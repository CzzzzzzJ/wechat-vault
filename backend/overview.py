"""Account-level aggregates over an explicitly bound immutable Skill snapshot.

Never reads message bodies. Counts physical stored records, not phone/cloud totals.
"""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def connect(path, root):
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Snapshot path outside account')
    if not path.is_file():
        raise FileNotFoundError(path.name)
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def columns(db, table):
    return {r[1] for r in db.execute('PRAGMA table_info(' + quote(table) + ')')}


def stamp(value):
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None
    except (ValueError, OverflowError, OSError):
        return None


class OverviewReader:
    def __init__(self, vault_root):
        self.root = Path(vault_root)
        self.cache = {}

    def read(self, source):
        # Directory ID is a fallback identifier, never presented as a verified nickname.
        username = re.sub(r'_[0-9a-f]{4}$', '', source.parent.name)
        result = {'status': 'not_read', 'nickname': None, 'username': username,
                  'identity_source': 'directory', 'conversation_count': None,
                  'group_count': None, 'message_count': None, 'group_message_count': None,
                  'unclassified_message_count': None, 'first_message_at': None,
                  'last_message_at': None, 'snapshot_at': None, 'recent_conversations': [],
                  'errors': [], 'coverage': 'local_snapshot_only', 'partial': False}
        for config in sorted((self.root / 'accounts').glob('*/config.json')):
            try:
                conf = json.loads(config.read_text())
                if Path(conf.get('db_dir', '')).resolve() != source.resolve():
                    continue
                pointer = json.loads((config.parent / 'current.json').read_text())
                sid = pointer.get('snapshot', '')
                if not re.fullmatch(r'[0-9a-f]{32}', sid):
                    raise ValueError('Invalid snapshot')
                snap = config.parent / 'snapshots' / sid
                if snap.is_symlink() or not snap.resolve().is_relative_to(config.parent.resolve()):
                    raise ValueError('Invalid snapshot path')
                manifest = json.loads((snap / 'manifest.json').read_text())
                cache_key = (str(source), str(snap), (snap / 'manifest.json').stat().st_mtime_ns)
                if cache_key in self.cache:
                    return self.cache[cache_key]
                result['snapshot_at'] = manifest.get('created_at')
                # Explicit account identity from the Skill config takes priority over directory ID.
                username = conf.get('account_username') or username
                result['username'] = username
                self._aggregate(snap, username, result)
                if not result['partial']:
                    if len(self.cache) >= 16:
                        self.cache.clear()
                    self.cache[cache_key] = result
                return result
            except FileNotFoundError:
                return result
            except (OSError, ValueError, TypeError, sqlite3.Error):
                result['status'] = 'unavailable'
                result['errors'] = ['无法读取该账号的快照，请检查快照完整性。']
                return result
        return result

    def _aggregate(self, snap, username, result):
        names = {}
        try:
            db = connect(snap / 'data/contact/contact.db', snap)
            try:
                cols = columns(db, 'contact')
                if 'username' not in cols:
                    raise ValueError('Unsupported contact schema')
                fields = [c for c in ('username', 'nick_name', 'remark') if c in cols]
                for row in db.execute('SELECT ' + ','.join(map(quote, fields)) + ' FROM contact'):
                    item = dict(row)
                    name = item.get('remark') or item.get('nick_name') or item['username']
                    names[item['username']] = name
                    if item['username'] == username and item.get('nick_name'):
                        result['nickname'] = item['nick_name']
                        result['identity_source'] = 'contact'
            finally:
                db.close()
        except (OSError, ValueError, sqlite3.Error):
            result['errors'].append('联系人资料不可用，部分名称暂以账号标识显示。')

        sessions = {}
        try:
            db = connect(snap / 'data/session/session.db', snap)
            try:
                if not {'username', 'last_timestamp'} <= columns(db, 'SessionTable'):
                    raise ValueError('Unsupported session schema')
                for row in db.execute('SELECT username,last_timestamp FROM SessionTable'):
                    if row['username']:
                        sessions[row['username']] = row['last_timestamp']
                result['conversation_count'] = len(sessions)
                result['group_count'] = sum(u.endswith('@chatroom') for u in sessions)
            finally:
                db.close()
        except (OSError, ValueError, sqlite3.Error):
            result['errors'].append('会话列表不可用，无法统计会话与群聊数量。')

        identities = set(names) | set(sessions)
        files = sorted(p for p in (snap / 'data/message').glob('message_*.db')
                       if re.fullmatch(r'message_\d+\.db', p.name))
        total = groups = unknown = 0
        earliest = latest = None
        counts = {}
        successful_tables = 0
        for path in files:
            try:
                db = connect(path, snap)
                try:
                    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if 'Name2Id' in tables and 'user_name' in columns(db, 'Name2Id'):
                        identities.update(r[0] for r in db.execute('SELECT user_name FROM Name2Id') if isinstance(r[0], str))
                    mapping = {'Msg_' + hashlib.md5(u.encode()).hexdigest(): u for u in identities if isinstance(u, str)}
                    for table in sorted(t for t in tables if re.fullmatch(r'Msg_[0-9a-fA-F]{32}', t)):
                        if 'create_time' not in columns(db, table):
                            result['errors'].append('部分消息表结构不支持，统计不完整。')
                            continue
                        count, start, end = db.execute('SELECT COUNT(*),MIN(create_time),MAX(create_time) FROM ' + quote(table)).fetchone()
                        successful_tables += 1
                        total += count
                        user = mapping.get(table)
                        if user is None:
                            unknown += count
                        elif user.endswith('@chatroom'):
                            groups += count
                        if user:
                            entry = counts.setdefault(user, {'count': 0, 'last': None})
                            entry['count'] += count
                            if end is not None:
                                entry['last'] = max(entry['last'] or end, end)
                        if start is not None:
                            earliest = min(earliest if earliest is not None else start, start)
                        if end is not None:
                            latest = max(latest if latest is not None else end, end)
                finally:
                    db.close()
            except (OSError, ValueError, sqlite3.Error):
                result['errors'].append('部分消息分库无法读取，统计不完整。')
        if not files:
            result['errors'].append('快照没有消息分库，无法统计消息量与覆盖日期。')
        if files and (successful_tables or not result['errors']):
            result.update(message_count=total, group_message_count=groups,
                          unclassified_message_count=unknown,
                          first_message_at=stamp(earliest), last_message_at=stamp(latest))
        result['recent_conversations'] = [
            {'name': names.get(u, u), 'kind': 'group' if u.endswith('@chatroom') else 'other',
             'message_count': counts.get(u, {}).get('count'),
             'last_message_at': stamp(counts.get(u, {}).get('last'))}
            for u in sorted((u for u in counts if counts[u]['count']>0), key=lambda u: counts[u]['last'] or 0, reverse=True)[:12]]
        result['partial'] = bool(result['errors']) or unknown > 0
        result['status'] = 'partial' if result['partial'] else 'ready'
        result['errors'] = list(dict.fromkeys(result['errors']))

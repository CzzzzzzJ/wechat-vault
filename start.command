#!/bin/sh
set -eu
cd "$(dirname "$0")"
DEFAULT_RUNTIME="$HOME/Library/Application Support/mdldm-wechat-vault/runtime/bin/python"
if [ -n "${VAULT_PYTHON:-}" ]; then
  PYTHON="$VAULT_PYTHON"
elif [ -x "$DEFAULT_RUNTIME" ]; then
  PYTHON="$DEFAULT_RUNTIME"
else
  PYTHON=python3
fi
"$PYTHON" -c 'import sys; sys.exit("需要 Python 3.10 或更新版本") if sys.version_info < (3, 10) else None'
exec "$PYTHON" -m backend.server "$@"

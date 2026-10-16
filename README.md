# 微信本地 Vault

本机微信聊天工作台：看账号、挖待办、出每日简报，再用 Codex 做语义搜索和问答。

macOS 微信 4.x · Python 3.10+ · 数据留本机

**主页：** [mdldm.club](https://www.mdldm.club) · **Skill：** [`mdldm-wechat-vault`](https://github.com/CzzzzzzJ/mdldm-skills/tree/main/skills/mdldm-wechat-vault)

喜欢就先 **[Star](https://github.com/CzzzzzzJ/wechat-vault)**，下面直接开跑。

---

## 先跑起来

```bash
git clone https://github.com/CzzzzzzJ/wechat-vault.git
cd wechat-vault
git clone https://github.com/CzzzzzzJ/mdldm-skills.git .local/mdldm-skills
python3 .local/mdldm-skills/skills/mdldm-wechat-vault/scripts/bootstrap.py
./start.command --skill-dir "$PWD/.local/mdldm-skills/skills/mdldm-wechat-vault"
```

浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。终端 `Ctrl+C` 停服务。

只要 Skill、不要界面：

```bash
npx skills add CzzzzzzJ/mdldm-skills --skill mdldm-wechat-vault
```

AI 搜索 / 问答还要装并登录 [Codex CLI](https://developers.openai.com/codex/cli/)。Skill 细节看 [这里](https://github.com/CzzzzzzJ/mdldm-skills/tree/main/skills/mdldm-wechat-vault)。已经装到 `~/.codex/skills/mdldm-wechat-vault` 的话，直接 `./start.command` 就行。

底层读取靠 Skill；本仓管界面、统计、缓存和 AI 编排。

---

## 能干啥

| 能力 | 说明 |
|------|------|
| 账号与概览 | 昵称、头像、消息覆盖日期、每日聊天活动 |
| 关系与事件 | 按日期抽待办、邀约、决策和进展，带原文 |
| 每日简报 | 当天该跟进的事 |
| 语义搜索 | Codex 扩词，在已导入文本里匹配，可筛日期 |
| 自然语言问答 | 理解问题 → 定位会话 → 读消息 → 回答 |
| 本地档案 | 本人介绍 + 沟通观察，按账号隔离 |

语音 / 图片 / 视频目前只计数。服务只听本机 `127.0.0.1`。

---

## 怎么用

1. 首页选账号，看清消息截止日期（快照时间 ≠ 聊到今天）。
2. 看每日活动、关系分析或简报；默认北京时间今天。
3. 搜索页用白话描述要找的事；日期留空 = 该账号已导入的全部文本。
4. 要更新数据就重新导入；报告和档案不会因切页丢。

---

## 配置（可选）

```bash
./start.command \
  --port 8765 \
  --source-root "/path/to/xwechat_files" \
  --vault-root "/path/to/vault-runtime" \
  --state-root "/path/to/web-state" \
  --skill-dir "/path/to/mdldm-wechat-vault" \
  --skill-python "/path/to/runtime/bin/python"
```

`source-root` 下要有 `<账号>/db_storage`。自定义 Python：`VAULT_PYTHON=/path/to/python ./start.command ...`。独立环境装本仓 `requirements.txt`，采集 / 解密还要 Skill 依赖。

---

## 二次开发

前端原生 HTML/CSS/JS，后端 Python 标准库 HTTP，解压用 zstandard。不用 npm 构建。

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

- [架构与接口](docs/ARCHITECTURE.md)
- [Agent 查询流程](docs/AGENT_FLOW.md)
- [开发与贡献](CONTRIBUTING.md)
- [安全问题反馈](SECURITY.md)

---

## 接下来你可以

1. **Star** 本仓，方便跟更新
2. **装 Skill**：`npx skills add CzzzzzzJ/mdldm-skills --skill mdldm-wechat-vault`
3. 教程 / 合作：[麦当的知识站](https://www.mdldm.club)
4. 微信：`gaozhizhaji778` · X：[@czzzzzzJ_](https://x.com/czzzzzzJ_)

合集仓里还有 `omi`（小红书笔记）、`mdldm-monetize`（变现诊断）：[mdldm-skills](https://github.com/CzzzzzzJ/mdldm-skills)

## 许可证

原创代码 [MIT](LICENSE)。Codex 名称与标识归 OpenAI；本项目不隶属腾讯或 OpenAI。

## 待办、进展与联系人

在每日简报或关系分析结果中点击“加入跟进 / 关联进展”，可以新建事项，也可以将本次聊天结论添加到已有事项的时间线。相同内容重复保存不会重复创建。

“待办与进展”支持待处理、进行中、等待对方、已完成、已取消，可设置或调整截止日期、修改负责人、填写进展备注，并筛选逾期和已结束事项。已完成事项也能重新打开。每次修改保留前后值与时间；AI 重新分析不会覆盖本人维护的状态。

“联系人”支持按姓名查找联系人或群，查看头像、最近可见 30 天的交流数量及关联事项。关联依据是会话标识；群聊事项归到群，不自动归到某个群成员。旧报告缺少会话标识时仅在名称唯一匹配后关联，同名无法确认时保留未关联状态。

事项及聊天依据单独保存在 `workflow/workflow.sqlite3`，按账号隔离。刷新、切换页面和服务重启后保留，移除分析缓存不会删除已保存的跟进事项。不会自动发送提醒、联系对方或创建日历事件。

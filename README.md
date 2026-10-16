# 微信本地 Vault

本机管自己的微信聊天记录：看账号、挖待办、出每日简报，再用 Codex 做语义搜索和问答。

**开发者预览 · macOS 微信 4.x · Python 3.10+**

数据留在本机。语音 / 图片 / 视频目前只计数，不做内容识别或播放。

---

## 先动手

```bash
git clone https://github.com/CzzzzzzJ/wechat-vault.git
cd wechat-vault
git clone https://github.com/CzzzzzzJ/mdldm-skills.git .local/mdldm-skills
python3 .local/mdldm-skills/skills/mdldm-wechat-vault/scripts/bootstrap.py
./start.command --skill-dir "$PWD/.local/mdldm-skills/skills/mdldm-wechat-vault"
```

打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。终端里 `Ctrl+C` 停服务。

底层读取靠 Skill [`mdldm-wechat-vault`](https://github.com/CzzzzzzJ/mdldm-skills/tree/main/skills/mdldm-wechat-vault)；应用只管界面、统计、缓存和 AI 编排。

只要 Skill：

```bash
npx skills add CzzzzzzJ/mdldm-skills --skill mdldm-wechat-vault
```

AI 功能还要装并登录 [Codex CLI](https://developers.openai.com/codex/cli/)。首次导入前看一眼 [Skill 说明](https://github.com/CzzzzzzJ/mdldm-skills/tree/main/skills/mdldm-wechat-vault)——macOS 可能拦进程访问，向导会告诉你怎么办。临时签名副本要你本人确认，不会改原微信。

已装到 `~/.codex/skills/mdldm-wechat-vault` 时，直接 `./start.command` 即可。

---

## 能做什么

| 能力 | 说明 |
|------|------|
| 账号与概览 | 真实昵称、头像、消息覆盖日期、每日聊天活动 |
| 关系与事件 | 按日期抽待办、邀约、决策和进展，带原文依据 |
| 每日简报 | 当天该跟进的事，和分析页共用持久缓存 |
| 语义搜索 | Codex 扩检索词，在已导入文本里匹配排序，可筛日期 |
| 自然语言问答 | 理解问题 → 匹配会话 → 读有限消息 → 回答 |
| 本地档案 | 本人确认的介绍 + 沟通观察，按账号隔离 |

语义搜索是检索词扩展，不是向量搜索，换说法可能漏。简报 / 分析默认：私聊消息量前 5、本人发言量前 3 个群；每会话最多前 1000 条，合计最多 60000 字符——不是全量穷尽，页面会标覆盖范围。关系标签是推测，待办和结论自己再核一遍。

---

## 日常怎么用

1. 首页选账号，看清消息截止日期（快照生成时间 ≠ 聊到今天）。
2. 看每日活动、关系分析或简报；默认北京时间今天，没消息就更新快照或换历史日期。
3. 搜索页用白话描述要找的事；日期留空 = 该账号全部已导入文本。
4. 要更新数据就重新导入；已有报告和个人档案不会因切页消失。

---

## 数据与隐私（必读）

- 只听 `127.0.0.1`，本人本机用，别直接丢公网。
- 原始库和密钥留本机；应用读 Skill 发布的快照，不改微信消息。
- 统计本机算。搜索的语义扩展只发「搜索需求」；原文检索在本机。
- 问答 / 简报 / 关系分析会把选定范围的会话名、发送者、时间、正文交给当前 Codex 配置的模型——**不是全离线 AI**。
- 分析缓存含原文依据，搜索索引含明文聊天，默认在 `~/Library/Application Support/mdldm-wechat-web`，当聊天数据保管。
- 本地快照 ≠ 手机 / 云端全部历史。

只处理你本人拥有或明确获授权的数据。提 Issue 用虚构样例，别上传聊天、库、密钥、索引、缓存或登录信息。

---

## 配置

```bash
./start.command \
  --port 8765 \
  --source-root "/path/to/xwechat_files" \
  --vault-root "/path/to/vault-runtime" \
  --state-root "/path/to/web-state" \
  --skill-dir "/path/to/mdldm-wechat-vault" \
  --skill-python "/path/to/runtime/bin/python"
```

`source-root` 下要有 `<账号>/db_storage`；`vault-root` 是 Skill 运行数据目录。`--codex-bin` 可指定 Codex。自定义 Python：`VAULT_PYTHON=/path/to/python ./start.command ...`。独立环境装本仓 `requirements.txt`，采集 / 解密还要 Skill 依赖。

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

兼容性以已识别的 macOS 微信 4.x 快照布局为准；微信版本、macOS 权限、Codex 协议一变就可能要适配。欢迎提交**不含私人数据**的复现步骤。

---

## 接下来你可以

1. **Star** 本仓，方便跟更新  
2. **装 Skill**：`npx skills add CzzzzzzJ/mdldm-skills --skill mdldm-wechat-vault`  
3. 看教程 / 合作：[麦当的知识站](https://www.mdldm.club)  
4. 微信：`gaozhizhaji778` · X：[@czzzzzzJ_](https://x.com/czzzzzzJ_)

合集仓里还有 `omi`（小红书笔记）、`mdldm-monetize`（变现诊断）：[mdldm-skills](https://github.com/CzzzzzzJ/mdldm-skills)

## 许可证

原创代码 [MIT](LICENSE)。Codex 名称与标识归 OpenAI；本项目不隶属腾讯或 OpenAI。

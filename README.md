# 微信本地 Vault

在本机管理自己的微信聊天记录，用 Codex 查找信息、整理待办和回顾沟通。

**开发者预览版 · macOS 微信 4.x · Python 3.10+**

## 功能

- **账号与数据概览**：真实昵称、头像、消息覆盖日期和每日聊天活动。
- **关系与事件分析**：按日期提取待办、邀约、决策和事项进展，提供原文依据。
- **每日简报**：集中查看当天需要跟进的事，与分析页共享持久缓存。
- **全局语义搜索**：Codex 扩展检索词，在当前账号的已导入文本中匹配和排序，支持日期筛选与原词搜索。
- **自然语言问答**：理解问题后匹配会话、读取有限范围的消息并生成回答。
- **本地个人档案**：保存本人确认的介绍及基于沟通统计的观察，按账号隔离。

语音、图片和视频目前仅作为消息记录计数，**不支持内容识别或播放**。语义搜索采用检索词扩展，尚未实现向量搜索，可能遗漏不同表达。

## 安装与启动

需要 macOS、Python 3.10+；AI 功能还需要安装并登录 [Codex CLI](https://developers.openai.com/codex/cli/)。

### 1. 获取应用与读取 Skill

```bash
git clone https://github.com/CzzzzzzJ/wechat-vault.git
cd wechat-vault
git clone https://github.com/CzzzzzzJ/mdldm-skills.git .local/mdldm-skills
```

底层读取能力由 [mdldm-wechat-vault](https://github.com/CzzzzzzJ/mdldm-skills/tree/main/skills/mdldm-wechat-vault) 提供，不依赖其他微信 CLI。Skill 负责环境配置、账号绑定、密钥采集、数据库与 WAL 解密及快照查询；应用负责界面、统计、缓存和 AI 编排。

### 2. 安装 Skill 的运行环境

```bash
python3 .local/mdldm-skills/skills/mdldm-wechat-vault/scripts/bootstrap.py
```

首次使用前阅读 [Skill 使用说明](https://github.com/CzzzzzzJ/mdldm-skills/tree/main/skills/mdldm-wechat-vault)。macOS 的进程访问权限可能阻止密钥采集；向导会提示处理方式。准备临时签名副本需要本人明确确认，不修改原微信应用。

### 3. 启动应用

```bash
./start.command --skill-dir "$PWD/.local/mdldm-skills/skills/mdldm-wechat-vault"
```

打开 [本地工作台](http://127.0.0.1:8765)。在终端按 `Ctrl+C` 停止服务。首次从首页选择账号并按向导导入：等待监听就绪后登录指定账号，密钥验证完成后正常退出微信，再生成快照。

如果已将 Skill 安装到 `~/.codex/skills/mdldm-wechat-vault`，可直接运行 `./start.command`。

## 日常使用

1. 在首页选择账号，确认消息截止日期。快照生成时间不代表聊天已同步到今天。
2. 查看每日活动、关系分析或简报。默认日期为北京时间的今天，没有消息时需更新快照或选择历史日期。
3. 在搜索页描述要找的事情；日期留空检索该账号全部已导入文本。
4. 需要更新数据时重新导入。已有报告和个人档案保留，不会因切换页面消失。

简报和范围分析目前选取私聊消息量前 5 位、本人发言量前 3 个群；每会话最多读取前 1000 条原始记录，合计最多 60000 字符。结果不是全部会话的穷尽分析，页面会标注覆盖范围。关系标签为推测，待办与结论需要核对。

## 数据与隐私

- 服务只监听 `127.0.0.1`，面向本人本机使用，不适合直接部署到公网。
- 原始数据库和密钥留在本机。应用读取 Skill 发布的快照，不修改微信消息。
- 统计在本机计算。搜索的语义扩展仅发送搜索需求；检索原文在本机完成。
- 问答、简报及关系分析会将选定范围的会话名、发送者、时间和聊天正文交给当前 Codex CLI 配置的模型服务。不是全离线 AI。分析页点击分析或修改日期、账号会触发分析；可复用缓存时直接恢复。
- 联系人头像会通过受限的微信图片域名获取。
- 分析缓存包含原文依据；搜索索引包含明文聊天。默认保存在 `~/Library/Application Support/mdldm-wechat-web`，应与聊天数据一样妥善保管。
- 本地快照不等于手机或云端全部历史。统计按物理记录计算，不保证跨分库去重。

仅处理本人拥有或明确获授权的数据。提交 Issue 时请使用虚构样例，不上传聊天、数据库、密钥、索引、缓存或登录信息。

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

`source-root` 下包含 `<账号>/db_storage`；`vault-root` 是 Skill 运行数据目录，区别于源码目录。`--codex-bin` 可指定 Codex 可执行文件。启动脚本优先使用 Skill 默认 runtime；自定义环境可用 `VAULT_PYTHON=/path/to/python ./start.command ...`。独立 Python 环境需安装本仓库的 `requirements.txt`；采集和解密还需 Skill 的依赖。

## 二次开发

前端为原生 HTML/CSS/JavaScript，后端使用 Python 标准库 HTTP 服务，文本解压使用 zstandard。无需 npm 构建。

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

- [架构与接口](docs/ARCHITECTURE.md)
- [Agent 查询流程](docs/AGENT_FLOW.md)
- [开发与贡献](CONTRIBUTING.md)
- [安全问题反馈](SECURITY.md)

当前兼容性以已识别的 macOS 微信 4.x 快照布局为限；微信版本、macOS 权限和 Codex CLI 协议变化都可能需要适配。尚未完成所有环境的安装验证，欢迎提交不含私人数据的复现步骤。

## 交流

- 知识站：[麦当的知识站](https://www.mdldm.club)
- 微信：`gaozhizhaji778`
- X：[@czzzzzzJ_](https://x.com/czzzzzzJ_)

## 许可证

项目原创代码使用 [MIT License](LICENSE)。Codex 名称及标识的权利归 OpenAI，不在本项目许可证授权范围内。本项目不隶属于腾讯或 OpenAI。

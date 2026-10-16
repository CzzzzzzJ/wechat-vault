# 模块与接口

```text
wechat-vault/
├── web/                  # 页面、样式、浏览器交互
├── backend/
│   ├── ingest.py         # 独立 Skill 读取管线适配、账号验证、错误和进度
│   ├── profile.py        # 本人资料、独立持久档案、新快照统计观察
│   ├── analysis.py       # 时间范围分析、关系/事件结构校验、类目计数
│   ├── agent.py          # 需求解析、范围校验、会话匹配与有界检索
│   ├── chat.py           # Skill history 适配、限量预览、账号绑定确认凭据
│   ├── activity.py       # 每日活动、逐分库本人归属、小时热力图
│   ├── overview.py       # 按账号读取快照、匹配昵称、聚合会话和消息统计
│   ├── database.py       # 文件元数据检测、基线比较、快照清单适配
│   ├── codex.py          # Codex 子进程、JSONL 事件、超时和取消
│   └── server.py         # HTTP 路由、会话、同源校验、静态文件
├── tests/                # 临时目录及替身 CLI 测试
├── docs/
└── start.command
```

前端只依赖 HTTP JSON 接口。检测模块不导入解密模块；Codex 模块不接收数据库路径或密钥。消息查询由 chat.py 适配独立 Skill，显式选择账号、日期和会话；解密逻辑不进入页面或 Codex 进程。

| 接口 | 用途 |
| --- | --- |
| GET /api/bootstrap | 建立本地会话，返回 CSRF token |
| POST /api/activity | 指定已发现 account_id 与 YYYY-MM-DD 日期，返回本地每日聚合 |
| POST /api/scan | 扫描源文件、读取账号概览并保存比较基线 |
| GET /api/codex/status | CLI 安装、登录及最近连接测试状态 |
| POST /api/codex/probe | 开始无数据连接测试 |
| POST /api/codex/ask | 提问；可选当前账号聚合统计 |
| GET /api/jobs/{id} | 获取运行状态与回答 |
| POST /api/jobs/{id}/cancel | 取消任务 |

写接口要求相同 Origin、会话 Cookie 和 `X-Vault-Token`。静态文件采用白名单，服务拒绝非本机 Host。此服务面向个人本机使用，不支持公网部署或多用户身份管理。

每次仅运行一个 Codex 任务，默认超时 180 秒，保留最多约 30 个内存任务。网络重连事件显示为进度，最终退出状态和回答决定是否成功。兼容性依赖本机 Codex CLI 的命令行及 JSONL 协议。

账号统计仅接受与源目录绑定的 Skill 快照。消息表通过会话标识的 MD5 表名映射分类；查询仅使用 COUNT / MIN / MAX，不 SELECT 消息正文。统计缓存绑定源账号、快照路径和清单修改时间；发布新快照自动换缓存，部分读取失败不缓存。前端切换账号时同时切换所有统计，并取消勾选模型上下文，避免沿用前一个账号的选择。

读取管线：POST /api/ingest {account_id} 启动选定账号任务；GET /api/ingest/{account_id} 返回阶段与错误。仅允许访问已发现的账号，不接受客户端传入任意目录或命令。捕获前校验微信主进程实际打开的账号目录；SOURCE_BUSY 要求用户正常退出微信，不能用活动源冒充离线副本。

首次导入交互由原生 dialog 承载。后端返回 step/status/code，前端仅映射提示，不自行判定成功。状态为 idle/running/waiting_user/completed/cancelled/failed。客户端退出通过 GET /api/wechat/state 检测，SOURCE_BUSY 等待期间确认无微信进程后续跑读取任务；其余异常需用户重试。

POST /api/ingest/repair 要求 consent=true 且无微信运行；仅操作固定的运行目录副本，校验临时签名后启动副本。POST /api/ingest/cancel 取消当前读取子进程。修复任务完成当前安全步骤后停止后续步骤，取消不回滚已发布快照。采集器通过 stderr 的 capture_status 事件报告 hook_ready，页面收到该事件才提示开始登录。

每日活动查询仅读取发送者、时间、消息类型和联系人显示名。日期边界固定 Asia/Shanghai，缓存包含账号、快照、日期和清单版本。前端用请求序号丢弃切换账号或日期后的旧响应，加载时隐藏旧统计；本人映射不完整时不显示伪零值。

会话接口：POST /api/chat/preview 接收 account_id/date/chat_id，要求该会话属于当前账号当天活动；通过 Skill history 获取消息并生成有时限的本地预览凭据。POST /api/chat/ask 接收 account_id/preview_id/consent/prompt，仅将服务端保存的已确认预览送入 Codex。前端不能直接提交任意模型上下文、文件路径或 SQL。文本作为不可信分析材料，CLI 继续禁用工具、应用、网页和文件访问能力。普通会话预览与回答保持内存存储；分析页报告采用下述持久缓存。

Agent 流程：POST /api/agent/plan 仅把用户问题与当前/所选日期交给 Codex，要求返回结构化意图。POST /api/agent/prepare 绑定原始任务与账号，严格验证意图、日期和范围，将模型结果映射为固定的本地读取操作。模型不能执行任意工具、SQL 或文件访问。多义会话返回候选项；无匹配不回退到无关会话。范围卡片复用 /api/chat/ask 与服务端预览凭据，确认后只发送已生成的有界材料。

范围分析路由：/api/analysis/overview 读取 1–31 天的本地聚合；/prepare 生成有界、多会话且同一快照的材料；/start 验证账号及确认凭据并启动结构化 Codex 分析；/result 绑定账号与任务，验证类目和消息引用，再计算类目数量。前端 analysis.html/js/css 与现有日概览分离。关系引用必须属于该私聊；群聊不产生双人关系标签。模型不能自行决定类目统计数字。

头像由 avatar.py 通过 /api/avatar 提供：客户端只传 account_id/chat_id，服务端查询绑定账号快照的联系人头像地址。白名单主机、HTTPS、禁用重定向、4 秒超时、300KB 上限、PNG/JPEG/WebP 签名校验、最多 256 项内存缓存。无任意 URL/路径代理；失败返回空图并使用姓名占位。


分析缓存由 analysis_cache.py 管理，使用事务性 SQLite，报告按账号/日期范围检索并保留各次成功版本；报告携带快照时间和提取规则签名。后台观察线程独立于浏览器轮询验证并写入结果，失败不覆盖旧版本。重启时将未完成任务标记 interrupted，不宣称能恢复已被结束的 CLI 进程。报告与引用落盘，未发送的预览及模型密钥不入缓存。/api/analysis/cache 恢复报告、任务状态和历史范围；/clear 归档当前范围；/undo 仅恢复该账号对应归档批次。所有接口复用本机会话及同源校验，不能查询其他账号。localStorage 只保存当天的视图条件。


分析页交互采用单次流水线：点击主按钮即调用 prepare → start → result，前端不再要求第二次确认。用户主动修改账号或日期后经 700ms 合并触发同一流程，复用有效缓存并恢复未完成任务；单纯排序只重排本地数据。页面固定说明所选聊天会提交给当前 Codex 模型服务。初次进入只加载统计/恢复缓存，不自动创建新模型任务。读取阶段取消后不会继续启动模型；模型阶段复用作业取消接口。

个人档案接口：POST /api/profile 仅接收已发现的 account_id，从显式绑定快照匹配本人 username，保存身份字段、头像和每快照一次的近期沟通统计；POST /api/profile/update 仅允许 role/bio/interests 三个本人确认字段，不允许修改源库身份。profile.js 处理账号切换、头像、编辑与积累记录；对异步旧响应进行账号/版本检查。原始消息正文不入档案。静态 Codex 标识用于显示提供连接能力的产品，标识权利归 OpenAI。


## 简报与全局搜索

`/brief` 复用 analysis.py 的范围准备、结果验证和持久缓存，不维护第二套事件推理。`/search` 由 search.py 管理账号绑定、快照版本、私有 SQLite 文本索引及检索。`insights.js` 负责两个页面的交互。

POST `/api/search` 接收 account_id/query/start/end/semantic。语义模式先创建 Codex 扩词任务，再通过 POST `/api/search/result`（account_id/job_id）获取检索结果；原词模式直接返回。索引按账号隔离，新快照重建，重建失败保留原文件并返回错误。最多展示 50 条命中，搜索范围不限于分析页的会话排名。当前语义任务与结果在服务内存保存，离开页面后需要重新发起或继续轮询；文本索引持久化。

# 本地二次开发指南（Custom Dev Guide）

> **本文件属于本地定制内容，不属于上游项目。** 任何参与本仓库开发的 AI 助手或开发者，在开始工作前请先完整阅读本文，并遵守其中的约定。

## 1. 仓库状态与远程配置

本仓库是 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的二次开发（定制）副本。当前配置了两个远程仓库：

| 远程名 | 地址 | 用途 |
|--------|------|------|
| `upstream` | https://github.com/AstrBotDevs/AstrBot.git | 官方上游，**只读**，仅用于 fetch 更新，**永远不要 push** |
| `origin` | git@github.com:lannickytang-lang/AstrBot.git | 本人（lannickytang-lang）的仓库，所有本地提交推送到这里 |

用 `git remote -v` 可随时核对。

## 2. 分支与提交约定

- `master`：上游镜像分支，只包含上游代码 + 本指南、启动脚本等少量本地定制，**不在这里开发功能**
- `dev`：**日常开发主分支**。二次开发默认直接在 dev 上进行，工作区平时应停在 dev
- 大型或试验性功能可从 dev 切出独立分支（命名如 `feat/xxx`），验证完成后再合并回 dev
- commit 信息遵循上游的 conventional commits 约定（`feat:` / `fix:` / `docs:` 等）
- 上游 `AGENTS.md` 中的代码规范（ruff 格式化、Google docstring、KISS 原则等）**继续适用**，定制代码也要遵守

## 3. 同步上游更新的标准流程

```bash
git fetch upstream                # 拉取官方最新代码（不合并）
git checkout master
git merge upstream/master         # master 吸收官方更新
git push origin master

git checkout dev
git merge master                  # 把官方更新带入开发主线
git push origin dev
```

**冲突处理原则**：优先保留上游逻辑，再在其之上重新套用本地定制；如果不确定如何取舍，停下来询问用户，不要擅自猜测。定制代码尽量走插件（见下节），正常情况下冲突很少。

## 4. 定制原则（重要）

1. **优先使用 AstrBot 插件机制实现定制功能**，不改动 `astrbot/core` 核心代码。插件安装在 `data/plugins/` 目录，开发方法参考官方文档（`docs/zh/`）及插件模板仓库。插件与核心解耦，上游升级几乎不会冲突
2. 确需修改核心代码时：改动尽量集中、少碰无关文件，**每个功能独立 commit**，方便上游合并时定位与排查
3. 不要修改或删除本文件
4. 每次新增定制（功能、核心改动、新配置），**必须在本文件第 5 节登记**

## 5. 定制记录（持续更新）

| 日期 | 分支 / commit | 定制内容 |
|------|---------------|----------|
| 2026-09-26 | master | 初始化二开环境：配置 upstream/origin 双远程、SSH 走 443、新增本指南 |
| 2026-09-26 | master | 新增一键开发启动脚本 `dev.bat` / `dev.ps1`（根目录，双击即同时启动前后端并打开浏览器） |
| 2026-09-26 | master, dev | 建立分支模型：master=上游镜像，dev=日常开发主线 |
| 2026-09-26 | dev | 固化本地构建产物（pnpm 12 lockfile 与 MDI 字体子集再生成），见第 6 节说明 |
| 2026-09-26 | dev | 配置微信自动回复全链路：DashScope embedding 服务商（dashscope_kb/text-embedding-v4）+ "悦音琴行知识库"（虚构示例，源文档在 `kb_docs/`）+ 人格 `yueyin`（店长助理小悦）+ 唤醒词 `AI`（私聊需 AI 开头才回复，webchat 豁免） |
| 2026-10-01 | dev | 新增缘声琴行真实知识库源文档 `kb_docs_yuansheng/`（6 篇，基于团购页截图整理，含信息边界文档防幻觉），用于替换示例"悦音琴行知识库"；截图原件在 `D:\tjs\tys\店铺\` |
| 2026-10-01 | dev | 服务器知识库切换为真实库：新建"缘声琴行知识库"（7 篇 / 37 分块，02 拆为 02a/02b 规避 DashScope embedding 批量上限 10 条），删除"悦音琴行知识库"，`kb_names` 已指向新库；人格 `yueyin` prompt 同步改为缘声琴行业务（21.8 元团购课，移除 49 元试听课规则，对齐 06 信息边界）。服务器操作走 dashboard API，配置均留 .bak |
| 2026-10-01 | dev | 转人工插件 `custom_plugins/kf_human_transfer/`（源码在仓库，已部署到服务器 data/plugins/）：关键词/管理台指令转接、人工期间 AI 静默、防回环（origin≠3 拦截）、24h 超时自动回收；指令 kf列表/kf状态/kf人工/kf恢复/kf记录（ADMIN 门禁）。关键事实：企微 `kf/service_state/trans` 的 service_state 是**目标状态**（3=人工+servicer_userid、4=结束），wechatpy 注释"当前状态"有误；管理台指令需 admins_id 含 dashboard 用户名（服务器已加 yuansheng），命令不带斜杠输入（唤醒词为 AI）。v0.2.1：全量聊天日志 chat_log.jsonl（权威分析数据源）+ 人工阶段消息同步写入 AstrBot conversations 表（带 [人工]/[系统] 前缀，管理台聊天记录页可见、AI 恢复时继承上下文；经 context.conversation_manager 的 get_curr_conversation_id/get_conversation/update_conversation API）；全量聊天日志 chat_log.jsonl（客户/店主/AI/系统四类，含时间戳；AI 回复经 on_decorating_result 钩子捕获；首次启动自动回填企微 3 天 sync_msg 存档）；消息 origin 实测语义 3=客户、5=店主接待回复、4=系统事件 |
| 2026-10-01 | dev | 数据分析菜单（获客营销分析）：左侧新增一级菜单 `/analysis`（i18n 四语言）。四维筛选（时间范围 created_after/before 新增，贯穿 sqlite→conversation_mgr→conversation_service→conversations API additive 参数）、会话列表+对话记录预览、按筛选导出 CSV(UTF-8 BOM)/JSONL（`POST /api/v1/analysis/export`）。AI 分析走双通道：`POST /api/v1/analysis/sessions` 创建预置 webchat 会话——筛选语料（≤50 会话×最近 40 条，剔除 system 注入与 analyst 自身会话防递归污染）注入 LLM 上下文层（展示层只插摘要卡片）、绑定 persona `marketing_analyst`（自动 seed，tools=[]），前端跳转 `/chat/<sid>?autoSend=<开场指令>` 自动发送（Chat.vue 增 maybeAutoSendFromRoute 钩子），多轮追问即普通聊天。场景指令模板存 `data/analysis_scenarios.json`（内置 4 场景：高意向挖掘/到店转化/流失挽回/经营洞察；编辑/新建/克隆/恢复默认/删除自定义，`/api/v1/analysis/scenarios*`）。前端新增 `views/analysis/AnalysisPage.vue` + `ScenarioEditDialog.vue`；API 客户端走 openspec/openapi-v1.yaml → pnpm generate:api → v1.ts analysisApi。镜像 1.1.0：新后端代码进镜像，dashboard/dist 需同步服务器 data/dist（assets/version=v4.28.1 兼容标记，缺失会触发官方 dist 下载覆盖） |
| 2026-10-02 | dev (worktree dev-cc-chat, 22b286a1d) | chat 接入 Claude Code 引擎（数据分析 agent 化，MVP 本地完成）：新增 provider `claude_code`（`sources/claude_code_source.py` + manager.py 显式 case + default.py 模板「Claude Code 引擎」）——spawn 无头 claude CLI（`-p --output-format stream-json --verbose --permission-prompts none`），会话映射 `data/claude_session_map.json` + `--resume` 续接（映射失效自动降级新会话重跑），deny 删除类命令 + 未白名单工具自动拒，模型后端继承本机 CLI 认证（当前 deepseek-v4-flash，base_url/api_key/model 可选覆盖）。`/场景名 描述` 前缀确定性触发分析场景；4 内置场景落盘 `data/skills/<场景名>/SKILL.md` 并 junction 进 `~/.claude/skills`（技能页→引擎双向互通）。chat 界面/历史/客服机器人链路零改动（provider 按会话选择，wecom 不受影响）。worktree 隔离开发（`run_worktree.py` 钉 sys.path——clone 的 .venv 会解析回主仓库）。实测：工具调用查库/追问续接/deny 拦截/技能可见/场景触发全通过；服务器部署与权限批准卡片为二期（方案：.omc/plans/claude-code-chat-integration-plan.md，桥接通用经验见 memory bridge-official-claude-code） |
| 2026-10-01 | dev | 客户昵称/头像接入分析链路（镜像 1.1.1）：消息流里只有 external_userid 不含微信名，昵称唯一来源是企微 `kf/customer/batchget`。新建核心表 `kf_customer_profile`（customer_id 主键/nickname/avatar，po.py+sqlite.py get/upsert，启动 create_all 自动建表）。**写入时机=客户首次发消息**：kf 插件 on_kf_message 里 `_ensure_customer_profile` 后台任务查表→缺失才调 batchget→入库（任何失败仅告警绝不阻塞消息链路）；**读取=表优先**：analysis_service.resolve_customer_names 读 kf_customer_profile，老客户缺失时补拉一次入库（分析页列表/记录预览显示头像+昵称、点击复制客户ID 供 kf人工 指令用；CSV 加"微信昵称"列；JSONL 加 customer_name；AI 语料每段标题带"（微信昵称：xxx）"并要求报告同时给 ID+昵称）。新增 `GET /api/v1/analysis/customer-names?ids=` |
| 2026-10-02 | dev | 转人工状态机 v0.3.1（无静默改造）：①人工中客户消息 3 分钟无店主回复→自动 trans 3→4 交还 AI（计时基准=客户最近一条消息，店主任意回复即重置）；②店主发「稍等」→本轮等待延长至 6 分钟；③触发转人工**先**发「正在召唤客服（预计3分钟）」**再** trans——顺序不能反，**企微硬规则：state 3/4 下机器人禁发消息（95018），仅 state 1 可发**（5 分钟后实测仍拒，非竞态）；④超时衔接话术写入 AI 上下文（客户下一条消息由 AI 结合应答，替代被平台禁止的主动推送）；⑤超时同时推企微应用消息提醒店主（message/send agentid 1000002，不受会话状态限制）；⑥AI 接管期间店主在企微发消息→自动切回人工（零操作接管）；⑦新客户首次消息发欢迎语（known_customers 集合从 chat_log 种子初始化，仅一次）。全部话术/时长在 WebUI 插件配置页可改。核心层新增 WeChatKF.send_msg 封装。deploy.py 部署 3 连跑（1134 全量→1142 修 95018 时序→1148 修通知通道） |

## 6. 本机环境注意事项

- 操作系统：Windows，shell 为 Git Bash，仓库位于 `D:\tjs\tys\AstrBot`
- 本机代理（Clash 类，fake-ip 模式）会拦截 github.com 的 **22 端口**，SSH 已配置改走 **443 端口**（见 `C:\Users\oyl\.ssh\config`），SSH 认证可用
- 克隆/拉取公开仓库可直接用 HTTPS；push 依赖 SSH（用户名 lannickytang-lang）
- 启动方式见上游 `AGENTS.md`：后端 `uv run main.py`（端口 6185），前端 `cd dashboard && pnpm dev`（端口 3000，`/api` 自动代理到 6185）
- **一键启动**：双击根目录 `dev.bat`（或 PowerShell 执行 `.\dev.bat`），自动弹出前后端两个日志窗口，约 20 秒后打开浏览器访问前端。停止服务：关闭对应窗口即可
- 环境工具链：Python 3.12 / uv / Node 24 / pnpm（已装好；依赖用 `uv sync` 和 `cd dashboard && pnpm install` 安装）
- **构建产物提示**：`dashboard/src/assets/mdi-subset/`（前端启动时自动再生成的图标字体）和 `dashboard/pnpm-lock.yaml` 会因本地 pnpm 版本较新而与上游不同，已在 dev 固化。上游同步若在这几个文件冲突，**不要手工合并**，以上游版本为准后运行 `cd dashboard && pnpm install && pnpm dev` 重新生成即可
- **知识库自动回复链路**（2026-09-26 配置）：
  - 知识库"悦音琴行知识库"（4 篇虚构文档 / 24 分块），源文档在 `kb_docs/`；接入真实资料时整理成同样结构的 md/docx/pdf 上传替换
  - Embedding：DashScope `text-embedding-v4`（来源 id `dashscope_kb`，需保证阿里云百炼账户不欠费）
  - 人格 `yueyin`（默认人格）：店长助理"小悦"，规则详见人格 system prompt；改话术在 WebUI"人格设定"页
  - 唤醒词：`platform_settings.friend_message_needs_wake_prefix=true` + `wake_prefix=["AI"]`，即微信私聊只有 AI 开头的消息才触发回复
  - 微信侧联调：用另一微信号给机器人发 "AI 钢琴课多少钱一节？" 验证

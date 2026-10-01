# Deep Interview Spec: Dashboard「数据分析」菜单 — 会话筛选 / 导出 / AI 营销分析

## Metadata
- Interview ID: di-dashboard-analysis-20261001
- Rounds: 6
- Final Ambiguity Score: 16%
- Type: brownfield（定制版 AstrBot fork，dev 分支，已部署于 yuansheng.tudodo.vip）
- Generated: 2026-10-01
- Threshold: 0.2
- Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.90 | 0.35 | 0.315 |
| Constraint Clarity | 0.88 | 0.25 | 0.220 |
| Success Criteria Clarity | 0.72 | 0.25 | 0.180 |
| Context Clarity | 0.85 | 0.15 | 0.128 |
| **Total Clarity** | | | **0.843** |
| **Ambiguity** | | | **0.157** |

## Topology
| Component | Status | Description | Coverage / Deferral Note |
|-----------|--------|-------------|--------------------------|
| 多维筛选会话 | active | 时间范围（新增）+平台（默认企微）+关键词+消息类型四维组合筛选会话 | 验收标准 2、8 |
| 筛选结果导出 | active | 按筛选条件整批导出 CSV（Excel 友好）与 JSONL | 验收标准 3 |
| 在线 AI 分析 | active | 筛选会话直接丢给当前聊天 LLM，结果 Markdown 在线展示 | 验收标准 5、7、8 |
| 营销提示词库 | active | 内置 ≥4 场景模板，在线编辑/另存/恢复默认/新建，可扩展 | 验收标准 4 |
| 分析历史留存 | active | 每次分析保存（筛选快照+模板+结果），可回看 | 验收标准 6 |
| 部署上线 | active | 重建 Docker 镜像并更新服务器容器，线上全链路可用 | 验收标准 9 |

（用户在 Round 0 明确选择 5 组件含部署上线；分析历史在 Round 5 并入在线 AI 分析的存储设计，此处单列以便跟踪。）

## Goal
在 AstrBot Dashboard 左侧新增「数据分析」一级菜单。店主（缘声琴行）通过 时间范围+平台+关键词+消息类型 组合筛选客户会话，将筛选结果一键导出（CSV/JSONL）或直接在线交给 AI 按内置营销场景提示词分析；分析结果以 Markdown 展示并保存历史可回看。首要价值路径：**筛出近期咨询客户 → AI 产出按意向排序的客户清单（含可直接复制的跟进话术）→ 店主对高意向客户转人工跟进**，最终提高到店率与成交率。提示词模板是一等公民，为后续大量分析场景预留扩展。

## Constraints
- 架构路线：**直接修改 dashboard**（Round 3 确认）。前端新增页面；后端在 `astrbot/dashboard/` 下以**新增文件为主**，对 upstream 文件的改动保持最小 additive；核心消息管道（astrbot/core pipeline）不动。
- 数据范围：全部平台会话，筛选器默认勾选企微（wecom）。
- 筛选维度边界（Round 6）：时间范围+平台+关键词+消息类型，四维足够，不做更多维度。
- 主验收路径优先（Round 4）：客户意向清单 + 导出必须完美；经营洞察可后续迭代，但模板机制必须可扩展（"后续会有很多分析场景"）。
- 分析输入保护（设计决策）：单次分析最多 50 个会话、每会话取最近 40 条消息、单条消息截断，超限自动截断并在结果中提示。
- LLM 调用：使用系统当前启用的聊天提供商（与机器人对话同源），后端一次性补全，非流式。
- 提示词与历史存储：`data/` 目录下文件化存储（JSON），不新增 sqlite 表、不动 core db 层表结构。
- 部署：走既有链路（本地构建镜像 → docker save|gzip → scp → load → compose up -d），先备份服务器 data 目录；**不 push upstream**。
- 平台兼容 Windows/Linux、Python 3.10+；路径用 pathlib；注释与日志用英文（代码内），UI 文案中文为主、i18n 4 语言补齐菜单键。
- 登记定制：CUSTOM_DEV_GUIDE.md §5 新增条目。

## Non-Goals
- 不做定时自动分析/推送通知（含邮件，用户此前明确拒绝邮件通知）。
- 不做分析结果页"一键转人工"按钮——沿用现有手段（企微 App / 管理台 `kf人工` 指令），分析页仅提供客户 ID 复制便利。
- 不做同一用户多会话的画像归一/合并。
- 不做消息内容语义向量筛选（只做关键词/结构化维度）。
- 不更新 upstream docs/zh docs/en 截图（本地 fork 定制，不向上游 PR；以 CUSTOM_DEV_GUIDE 登记替代）。

## Acceptance Criteria
（✓=已验证；验收以 Revision v2 双通道架构为准，5/6 两条被 v2 修订替代）
- [x] 1. 左侧出现「数据分析」一级菜单（i18n 四语言键已补齐：zh-CN 数据分析/en-US Data Analysis/ja-JP データ分析/ru-RU Анализ данных；路由 /analysis，dashboard build 通过）。
- [x] 2. 筛选器：时间范围（今天/近7天/近30天/自定义起止）+平台（默认勾选 wecom，选项来自 filter-options）+关键词+消息类型；分页列表；本地实测 created_after/created_before 生效（30 天窗口 2 条、1970 窗口 0 条）。
- [x] 3. 按筛选导出 CSV（UTF-8 BOM ✓、列=客户ID/平台/会话ID/标题/时间/角色/内容 ✓）与 JSONL（含完整 content 结构 ✓），本地实测通过。
- [x] 4. 内置 4 个营销场景模板（高意向挖掘/到店转化/流失挽回/经营洞察），编辑/新建/恢复默认/删除自定义全部 REST 实测通过（内置删除被正确拒绝）。
- [~] 5.（v2 修订）在线分析=创建预置 webchat 分析会话：语料注入 LLM 上下文层 ✓、persona marketing_analyst 自动 seed 并绑定 ✓、摘要卡片写展示层 ✓、前端跳转 /chat/<sid>?autoSend= 自动发开场指令（本地构建通过；流式分析+追问待线上实测）。
- [x] 6.（v2 修订）分析历史=聊天会话列表（display_name="AI分析 · 场景名"，可在 /chat 回看），无自建存储。
- [x] 7. 输入保护：≤50 会话/每会话最近 40 条/单消息 400 字/总语料 30 万字截断；<system 注入剔除实测通过（含拼接在消息尾部的 system_reminder）；递归污染（分析会话被当客户语料）已修复并实测。
- [x] 8. 主验收路径端到端：线上 REST 实测通过（近7天+企微+关键词"价格"→ intent 场景创建分析会话成功；流式报告质量待店主实际体验）。补充迭代（同日，镜像 1.1.1）：客户微信昵称/头像接入——新表 kf_customer_profile（客户首次发消息时 kf 插件后台拉取入库，失败不阻塞）、分析页显示头像+昵称（点击复制客户ID）、CSV/JSONL/AI语料均带昵称；线上原验收状态不变"近 7 天+企微+关键词价格 → 高意向客户挖掘 → 意向清单+话术 → 追问"。
- [ ] 9. 服务器部署更新（镜像 1.1.0 + data/dist 同步，先备份），线上 yuansheng.tudodo.vip 全链路实测通过。
- [x] 10. ruff check/format 全绿；openapi-v1.yaml 新增 6 端点+4 schema，pnpm generate:api 生成成功；CUSTOM_DEV_GUIDE.md §5 已登记。

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| 只分析企微会话 | 问：管理台测试对话是否污染分析 | 全部平台可选，默认勾选企微（webchat 测试对话默认不选） |
| 输出一种结果形态 | 逆向：只要清单还是要洞察 | 两种都要，但**清单+导出是必须完美路径**，洞察可迭代 |
| 功能做成插件 iframe 页 | 引用代码证据（iframe+桥接成本） | 直接改 dashboard，新增文件为主 |
| 结果看完即走 | 问留存价值 | 保存历史可回看 |
| 筛选器越多越好 | 极简模式挑战 | 四维度足够，其余后补 |
| 提示词写死两个模式 | 用户："后续会有很多分析场景" | 模板为一等公民：内置 4 个 + 新建/克隆/编辑/恢复默认 |

## Technical Context（代码库探索结论）
- 菜单：`dashboard/src/layouts/full/vertical-sidebar/sidebarItem.ts`（新增一级项）；`sidebarCustomization.js#resolveSidebarItems` 会自动把新默认项带给存量用户；i18n 键在 `dashboard/src/i18n/locales/*/core/navigation.json`（4 语言）。
- 路由：`dashboard/src/router/MainRoutes.ts` 新增 `/analysis` 懒加载页面 `views/analysis/AnalysisPage.vue`。
- 复用：后端 `astrbot/dashboard/api/conversations.py` 已有 list/filter-options/export(按勾选)；`ConversationWorkspacePage.vue` 的筛选面板与选择模型可参考；`ConversationHistoryPreview.vue` 的消息解析可参考。
- **缺口**（需新增）：时间范围参数（conversations.py → conversation_service → conversation_mgr → core/db/sqlite.py 的 `get_filtered_conversations`，各 +2 行 additive）；按筛选条件导出；AI 分析端点（dashboard 首个直接 LLM 调用，走 `core_lifecycle.star_context.llm_generate()` 或 `provider_manager.get_using_provider_async()` + `text_chat`）；提示词模板 CRUD 与历史存储（data/ 下 JSON 文件，参考 `custom_plugins/kf_human_transfer` 的 state.json 模式）。
- API 客户端：改 `openspec/openapi-v1.yaml` → `cd dashboard && pnpm generate:api` → `dashboard/src/api/v1.ts` 加 façade。
- 部署：`deploy/docker-compose.yml` 镜像版本号升级（1.0.0 → 1.1.0），沿用 docker save|gzip → scp /root/images/ → load → compose up -d 链路，data 卷先备份。

### 内置提示词模板设计要点（顶级销售/营销专家视角，实现时展开为完整模板）
1. **高意向客户挖掘**（主场景）：评分维度=需求明确度/预算信号/时间紧迫性/决策人信号/到店意愿；输出=按意向分排序的客户表格（客户ID、S/A/B/C 等级、意向乐器课程、预算与顾虑、推荐跟进动作、可直接复制的下一句微信话术）+ 重点客户解读。
2. **到店转化跟进**：识别"咨询未到店"客户，输出邀约策略与专属钩子（21.8 元团购体验课/到店礼/限时性），每客户给到店邀约话术。
3. **流失预警挽回**：识别有意向信号但已冷却的客户，输出挽回优先级与开场话术（新优惠/新课程/关怀切入）。
4. **经营洞察报告**：咨询热点 TOP、价格异议归类、流失原因、转化漏筒、知识库缺口建议。
共同原则：只依据会话事实不编造；每条结论标注依据；输出可直接执行（话术可复制）；中文输出。

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| Conversation（会话） | core domain | user_id(UMO), platform, title, history, created_at/updated_at | 被 Filter 筛出，构成 AnalysisInput |
| FilterCondition（筛选条件） | core domain | 时间范围, platforms, keyword, message_type | 产出 Conversation 集合；被 Export/Analysis 引用 |
| ExportTask（导出） | supporting | format(csv/jsonl), 条件快照 | 消费 Filter 结果 |
| AnalysisRecord（分析历史） | core domain | id, created_at, 条件快照, 模板名, 会话数, result_md | 由 AnalysisRun 产生 |
| PromptTemplate（提示词模板） | core domain | id, name, scene_desc, system_prompt, user_prompt, built_in, updated_at | 驱动 AnalysisRun；可编辑/克隆/新建 |
| Platform（平台） | supporting | id(wecom/webchat/...), type | Filter 维度 |
| AnalysisRun（在线分析执行） | core domain | filter, template, LLM provider, 输入保护参数 | 产出 AnalysisRecord |

## Ontology Convergence
| Round | Entity Count | New | Changed | Stable | Stability Ratio |
|-------|-------------|-----|---------|--------|-----------------|
| 1 | 7 | 7 | - | - | - |
| 2 | 10 | 3 | 0 | 7 | 70% |
| 3 | 10 | 0 | 0 | 10 | 100% |
| 4 | 11 | 1 | 0 | 10 | 91% |
| 5 | 12 | 1 | 0 | 11 | 92% |
| 6 | 12 | 0 | 0 | 12 | 100% |

## Revision v2：双通道架构（用户在访谈后追加决策，2026-10-01）

用户指出 dashboard 已有 #/chat 多轮聊天窗口，确认复用它承担 AI 分析部分。**以下修订取代上文冲突条款**：

### 架构
- **数据分析页（新菜单）只负责"取数"**：四维筛选（时间/平台/关键词/消息类型）+ 会话列表预览 + 按条件导出 CSV/JSONL + 分析场景选择。
- **AI 分析 = 发起聊天会话**：「开始分析」→ 后端创建 webchat 会话（precedent: `ChatService.create_thread`）→ 语料注入 **LLM 上下文层**（conversations.history，展示层只插一张摘要卡片，界面不显示原始语料）→ 绑定「营销分析师」人格（conversation.persona_id）→ 前端跳转 `#/chat/:sessionId` 并自动发送开场指令 → 分析在聊天中**流式输出、可多轮追问**。
- **分析历史 = 聊天会话列表**（不再自建历史存储）。
- **提示词在线编辑分两层**：角色与专业要求 = 人格（「人格设定」页编辑，内置"营销分析师"人格）；分析角度与输出结构 = **场景指令模板**（数据页内 4 个内置：高意向挖掘/到店转化/流失挽回/经营洞察，可编辑/另存/新建，存 `data/analysis_scenarios.json`）。

### 被替代（原方案砍掉）
- ~~自建分析结果 UI（Markdown 渲染/复制）~~ → 聊天窗口自带
- ~~分析历史存储~~ → 聊天会话列表
- ~~提示词 CRUD 全套~~ → 人格页 + 轻量场景模板 JSON
- ~~后端直调 LLM 端点~~ → 走聊天管线（SSE 流式、工具、上下文压缩全部免费获得）

### 后端新增/改动（最终范围）
1. 时间范围参数贯穿现有会话查询链路（conversations.py → service → conversation_mgr → sqlite.py，additive）
2. `POST /api/v1/analysis/export`（按筛选条件导出 CSV[UTF-8 BOM]/JSONL）
3. `POST /api/v1/analysis/sessions`（筛选→语料压缩[≤50会话/每会话最近40条/剔除system]→注入上下文→绑人格→插摘要卡片→返回 session_id）
4. 场景模板读写端点（list/save/create/restore）
5. 「营销分析师」人格 seed（首次部署自动写入）

### 验收标准修订
- 原 5/6/7 条合并替换为：**「开始分析」自动跳转 #/chat，AI 以营销分析师人格流式输出首份分析；语料不出现在界面气泡中；追问"给S级客户各写3条话术"能得到上下文正确的回答；分析会话可在会话列表回看。**
- 其余验收条款（菜单/筛选/导出/场景模板/部署/登记）不变。

### 页面布局 v3（用户迭代确认）
- 顶部：筛选卡（纯取数：时间/平台/关键词/消息类型 + 命中计数 + 重置；导出移至底部行动栏）
- 中部双栏：左=会话列表（勾选 + 点击选中，选中行高亮）；右=**选中会话的完整对话记录预览**（客户/AI 气泡，复用 ConversationHistoryPreview 解析逻辑），无选中时显示空态提示
- 底部：**吸底行动栏**（sticky）：分析场景下拉 + 场景指令编辑入口 + 范围切换（全部筛选/仅勾选，勾选数实时联动）+ 导出下拉（CSV/JSONL）+ 开始分析（跳转 #/chat）
- 栏下方小字说明：分析会话机制与输入上限

### 关键实现事实（探索已证实）
- webchat 走完整管线（人格/工具/KB/插件），persona 经 `conversation.persona_id` 或会话级规则绑定（`PersonaManager.resolve_selected_persona`）
- 展示层（platform_message_history）与 LLM 上下文层（conversations.content）分离，支持只注入不改界面
- `ChatService.create_thread` 是预填上下文创建会话的现成先例
- 上下文超长由 `ContextManager` 自动截断/压缩，无需自建
- AstrBot 无 "skills" 机制；等价能力=插件工具/MCP/人格工具集/子代理编排（已向用户说明）

## Interview Transcript
<details>
<summary>Full Q&A (6 rounds)</summary>

### Round 0（拓扑确认）
**Q:** 5 组件拆分（筛选/导出/AI分析/提示词库/部署上线）是否正确？
**A:** 5 组件（含部署上线）。（首轮 AskUserQuestion 未答，重发后作答）
**Ambiguity:** 未评分

### Round 1（数据范围）
**Q:** AI 分析的输入会话范围是什么？
**A:** 全部平台，默认选中企微。
**Ambiguity:** 56%

### Round 2（分析产出形态）
**Q:** 期望拿到什么形态的结果？
**A:** 两种都要（客户意向清单 + 经营洞察报告，不同模板不同输出结构）。
**Ambiguity:** 51%

### Round 3（架构路线）
**Q:** 新功能代码放哪里？（证据：插件 iframe 桥接成本高；本 fork dashboard 零本地改动；定制规则偏好）
**A:** 直接改 dashboard（推荐方案）。
**Ambiguity:** 41%

### Round 4（验收主路径，逆向挑战）
**Q:** 如果只能保一条端到端路径完美工作，保哪条？
**A:** "1/3 先，注意设计好，后续会有很多分析场景的"（意向清单+导出优先；模板机制需可扩展）。
**Ambiguity:** 27%

### Round 5（结果留存）
**Q:** AI 分析结果需要保存供以后回看吗？
**A:** 保存历史可回看。
**Ambiguity:** 21%

### Round 6（筛选维度，极简挑战）
**Q:** 筛选器做到哪个程度？
**A:** 四维度足够（时间范围+平台+关键词+消息类型）。
**Ambiguity:** 16% ✅
</details>

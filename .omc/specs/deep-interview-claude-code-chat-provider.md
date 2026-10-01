# Deep Interview Spec: chat 模块接入 Claude Code 引擎（数据分析 agent 化）

## Metadata
- Interview ID: di-cc-chat-provider-20261002
- Rounds: 3（含 Round 0 拓扑 + 诉求复述确认）
- Final Ambiguity Score: 18.75%
- Type: brownfield
- Generated: 2026-10-02
- Threshold: 0.2 / Threshold Source: default
- Initial Context Summarized: no
- Status: PASSED

## Clarity Breakdown
| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Goal Clarity | 0.85 | 0.35 | 0.298 |
| Constraint Clarity | 0.80 | 0.25 | 0.200 |
| Success Criteria Clarity | 0.75 | 0.25 | 0.188 |
| Context Clarity | 0.85 | 0.15 | 0.128 |
| **Total Clarity** | | | **0.8125** |
| **Ambiguity** | | | **0.1875** |

## Topology
| Component | Status | Description | Coverage |
|-----------|--------|-------------|----------|
| claude-code 提供商适配器 | active | 注册 CHAT_COMPLEPTION 提供商，spawn 无头 claude CLI、stream-json 流式解析、UMO→claude session 映射、GLM 端点 | 验收 1/2 |
| 权限交互 | active(MVP 简化) | MVP=禁删除类命令（deny 规则+系统提示词约束只读）；二期=MCP 权限服务+聊天内批准卡片 | 验收 1 |
| 技能同步 | active | 软链接打通 AstrBot 技能页 data/skills ↔ claude ~/.claude/skills（Windows junction/服务器 ln -s），双向生效 | 验收 1 |
| 本地验收+服务器部署 | active(部署二期) | MVP 本地三链路验收；服务器部署为二期预案写入文档 | 二期 |
| 完整方案文档 | active | 用户明确要求的 md 交付物（本 spec 整合为 plan 文档） | 交付物 |

## Goal
在 AstrBot #/chat 中新增「Claude Code 引擎」提供商：后端 spawn 官方 claude CLI 无头模式（`-p --output-format stream-json --resume`），模型经 GLM 兼容端点；使店主在聊天里用自然语言让 agent 真实查询 data_v4.db/chat_log.jsonl 完成数据分析（可追问）、用 /场景名 触发场景、平台技能页增改的技能即时同步生效。chat 的历史记录与对话界面沿用（前端仅可能微调 provider 显示），微信客服机器人链路零改动。

## Constraints
- 客服机器人（wecom 平台 + 小缘人格 + 现有 provider 配置）**一行不动**；新能力只通过「提供商」这一标准扩展点注入
- chat 模块前端（会话列表/流式/历史）沿用，不做大改
- 模型走 GLM 兼容端点（ANTHROPIC_BASE_URL/AUTH_TOKEN 环境变量），可随时换端点（ccswitch 思路）
- MVP 权限：禁止删除类命令（rm/del 等 deny 规则），系统提示词约束"数据库只读"；权限卡片二期
- 技能同步用软链接（不写同步服务）
- 本地先行验收；服务器部署二期（文档给预案）
- 适配器代码放 astrbot/core/provider/sources/（或同等扩展位），遵循 fork 定制规范并登记 CUSTOM_DEV_GUIDE §5

## Non-Goals
- 不改客服机器人问答链路、不动转人工插件
- 不自建 agent 引擎（记忆/上下文/工具循环全部交给 Claude Code 官方）
- 权限批准卡片、服务器部署、数据分析页跳转会话引擎化 → 二期
- 不做图片/语音输入（MVP 文本）

## Acceptance Criteria（MVP）
- [ ] 1. 本地 #/chat 会话选择 Claude 引擎提供商 → 输入"分析近7天问过价格的客户"→ agent 实际调用工具（bash/sqlite 等）查询 data_v4.db → 输出含真实数字的报告 → 同会话追问有效（--resume 续接）
- [ ] 2. 输入 /高意向挖掘 近7天价格 类消息 → 确定性命对应场景并按场景指令分析
- [ ] 3. 在 AstrBot 技能页新增/修改技能 → 新聊天会话中立即可被 agent 使用（软链生效）
- [ ] 4. 客服机器人回归：微信客服消息仍走原 provider 正常回复（零影响验证）
- [ ] 5. 删除类命令被拒绝且聊天内可见"被拦截"提示
- [ ] 6. ruff/构建通过；方案文档 + CUSTOM_DEV_GUIDe §5 登记完成

## Assumptions Exposed & Resolved
| Assumption | Challenge | Resolution |
|------------|-----------|------------|
| chat 是半成品要重做 | 复述诉求时纠正 | 沿用 chat 界面与历史，只换引擎通道 |
| /技能名 需要平台级命令系统 | 调研证伪：原生无斜杠桥 | 适配器层确定性识别 /场景名（原生技能+场景 SKILL.md 化） |
| 技能需自建同步服务 | 用户提议软链接 | 采纳：junction/ln -s 双向生效，两边同构 SKILL.md |
| 无头不能问人 | 源码+CLI 帮助验证 | --permission-prompts host / permission-prompt-tool 可打通；MVP 先 deny 删除类 |
| 主目的是通用 agent | 用户澄清 | 本次主要目的=chat 支持数据分析 |

## Technical Context（本会话已探明）
- Provider 扩展点：`@register_provider_adapter(name, desc, provider_type=ProviderType.CHAT_COMPLETION)`；chat 前端已有 provider/模型选择器（Chat.vue `selectedProvider/selectedModel` 经 extra 传给管线 `_select_provider`）→ **前端零改动即可选新引擎**
- webchat 全管线与 SSE 流式已通；历史存 conversations 表（provider 忽略管线 contexts、只传最新消息+--resume，避免双份上下文重复）
- CLI 2.1.275 已验证参数：`-p --output-format stream-json --resume <id> --permission-prompts <host|none> --permission-prompt-tool <mcp> --allowed-tools/--disallowed-tools`
- CloudCLI 参考：`canUseTool` 挂起→WS 推前端→决策回流（二期对标）
- 引擎凭证：ANTHROPIC_BASE_URL=open.bigmodel.cn/api/anthropic + 现有 GLM key（本机已用于 CloudCLI 验证）
- skills 目录：claude 读 `~/.claude/skills`；AstrBot 技能页管 `data/skills`；格式同构（SKILL.md+frontmatter）
- 数据源：本地 `data/data_v4.db`（conversations、kf_customer_profile）、服务器 `data/plugins/kf_human_transfer/chat_log.jsonl`

## Ontology (Key Entities)
| Entity | Type | Fields | Relationships |
|--------|------|--------|---------------|
| ClaudeCodeProvider | core | id, spawn 参数, session_map | 被 ChatSession 选择；spawn ClaudeSession |
| ClaudeSession | core | claude_session_id, umo, cid | 映射 ChatSession |
| ChatSession | existing | webchat session | 选 Provider；存 History |
| GLMEndpoint | external | base_url, token, model | 驱动 ClaudeCodeProvider |
| PermissionPolicy | core | deny 规则, 只读约束 | 作用于 spawn 参数 |
| SkillsDir(symlink) | core | data/skills ↔ ~/.claude/skills | 双向同步技能 |
| ScenarioSkill | core | /场景名 → SKILL.md | 由 ScenarioTemplate 落盘 |
| DataSource | external | data_v4.db, chat_log.jsonl | 被 agent 工具读取 |
| 客服机器人 | existing | wecom+小缘 | 零改动约束 |

## Ontology Convergence
| Round | Count | New | Stable | Ratio |
|-------|-------|-----|--------|-------|
| 1 | 9 | 9 | - | N/A |
| 2 | 9 | 0 | 9 | 100% |

## Interview Transcript
<details><summary>Q&A（3 轮）</summary>

**R0 拓扑**：4 组件确认 → 用户追问技能同步 + 要求复述最终诉求 → 复述确认（补充：客服机器人不可动；主目的=chat 支持数据分析；界面历史沿用）→ 5 组件锁定
**R1 分析交互形态**：答"都要"（NL 查库 + /场景名 + 页面跳转引擎化[二期]）；技能同步提议软链接 → 采纳
**R2 MVP 验收线**：答"选1（本地三链路全通），权限暂时不允许执行删除命令即可"

</details>

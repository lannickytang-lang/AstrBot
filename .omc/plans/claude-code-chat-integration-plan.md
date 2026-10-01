# AstrBot chat 模块接入 Claude Code 引擎 —— 完整实施方案

> 版本：v1.0（2026-10-02，深度访谈定稿，歧义度 18.75%）
> 规格：`.omc/specs/deep-interview-claude-code-chat-provider.md`
> 状态：**待审批** —— 确认后开工

---

## 0. 最终诉求（一句话）

在 AstrBot 聊天窗口里拥有一个"真 agent"：引擎用 Claude Code 官方内核（记忆/上下文/工具循环/skills 全官方管理），模型走可切换的兼容端点（现为智谱 GLM），**首要场景是让店主在 chat 里用自然语言完成客户数据分析**；chat 界面与历史沿用，微信客服机器人零改动。

## 1. 总体架构

```
┌────────────────────────── AstrBot（现有，基本不动）──────────────────────────┐
│  #/chat 前端（沿用：会话列表/流式/历史/provider 选择器）                        │
│      │ 消息 + selectedProvider="claude_code"                                  │
│      ▼                                                                        │
│  webchat 管线（沿用：人格→process_stage→provider 路由）                         │
│      │ _select_provider 命中新适配器                                           │
│      ▼                                                                        │
│  ┌───────────────── ClaudeCodeProvider（新，唯一核心新增）──────────────────┐  │
│  │ 会话映射: (umo,cid) → claude_session_id（首条消息后捕获并落库）           │  │
│  │ spawn: claude -p "<最新消息>"                                             │  │
│  │        --output-format stream-json --verbose                              │  │
│  │        --resume <claude_session_id>                                       │  │
│  │        --disallowed-tools <删除类deny规则>                                 │  │
│  │        --append-system-prompt "<角色+数据库只读约束>"                      │  │
│  │        (env: ANTHROPIC_BASE_URL/AUTH_TOKEN → GLM)                         │  │
│  │ 解析 stream-json → 文本增量/工具调用卡片 → 异步流式回传                     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  技能同步: ~/.claude/skills ──junction/ln -s──> <astrbot>/data/skills         │
│  （技能页增改技能 → 引擎下次会话即可用；反向亦然）                               │
└──────────────────────────────────────────────────────────────────────────────┘
        │                          │                        │
        ▼                          ▼                        ▼
  官方 claude CLI（本机已装 2.1.275）   GLM 兼容端点           数据源（agent 用工具读）
  记忆=CLAUDE.md/自动压缩            open.bigmodel.cn       data/data_v4.db
  工具循环/skills=官方                 （可随时换端点）         chat_log.jsonl 等
```

**关键设计原则：只用标准扩展点。** 新代码 = 1 个 provider 适配器文件 + 1 条软链接 + 场景 SKILL.md 落盘。管线、前端、客服链路全部零改动。

## 2. 组件一：ClaudeCodeProvider 适配器（核心，约 250 行）

**注册**（仿 `dashscope_embedding` 模式）：
```python
@register_provider_adapter("claude_code", "Claude Code 引擎（官方 CLI 无头模式）",
                           provider_type=ProviderType.CHAT_COMPLETION)
class ClaudeCodeProvider(SourceProvider):
```
- 配置项（default.py schema + WebUI 提供商表单）：`cli_path`(默认"claude")、`base_url`、`api_key`、`model`(默认 glm-5.3)、`cwd`(agent 工作目录，默认 AstrBot 数据目录)、`max_turns`、`timeout_sec`(默认 600)、`deny_rules[]`(默认删除类)
- 提供商在管理台「模型提供商」页配置；chat 前端 provider 选择器**原生就会出现它**（Chat.vue 已传 selectedProvider，前端零改动）

**每条消息的执行流**：
1. 查映射 `(umo, cid) → claude_session_id`（存 sqlite 新表 `provider_session_map`，或复用 sp；无则不带 `--resume`）
2. 组装命令：
   ```
   claude -p "<message_str>" --output-format stream-json --verbose
          --resume <sid>                        # 有映射时
          --disallowed-tools "Bash(rm:*)" "Bash(del:*)" "Bash(rmdir:*)" "Bash(mkfs*)" ...
          --append-system-prompt "<营销/分析助手角色 + 数据库只读 + 输出中文报告>"
   ```
   环境：`ANTHROPIC_BASE_URL/AUTH_TOKEN/MODEL` 来自提供商配置
3. 异步逐行读 stdout JSON，翻译为 AstrBot 流式事件：
   - `assistant` 消息块 → 文本增量
   - `tool_use`/`tool_result` → `[🔧 正在执行: sqlite3 查询…]` 状态行（随结果更新成功/失败摘要）
   - 首个带 `session_id` 的事件 → 写映射
4. 进程退出（result 事件）→ 收尾；超时 kill 并提示；stderr 异常回传友好错误
5. **上下文策略**：忽略管线传入的 `contexts`（历史由引擎 `--resume` 自管），只发最新一条——避免双份历史重复与 token 浪费；AstrBot 侧 conversations 表照常存展示副本（供回看，不参与喂模）

**与现有系统的隔离**（客服机器人零改动的保证）：
- provider 路由按会话选择：webchat 会话选了 `claude_code` 才走新链路；wecom 平台的消息仍按其配置用原 provider，代码路径完全不交叉
- 不修改 `astr_main_agent.py`/管线任何一行（`_select_provider` 本就优先 extra 里的 selectedProvider）

## 3. 组件二：权限策略

**MVP（本期）**：
- `--disallowed-tools` 硬 deny：删除类（`Bash(rm:*)`、`Bash(del:*)`、`Bash(rmdir:*)`、`Bash(mkfs*)`、`Bash(git push:*)`）——被拦时引擎会向模型返回拒绝，聊天里自然显示"该命令被禁止"
- 系统提示词软约束："数据库文件为只读资产，任何写入/删除/结构变更一律禁止；分析只读查询"
- 默认 `--permission-prompts none`（无宿主时询问=自动拒绝）+ 白名单放行只读工具（Read/Grep/Glob/Bash 只读命令）——即"默认问不了=拒绝"，靠 deny+白名单组合出"只许读、禁删除"的安全区

**二期（预案，本期不做）**：
- 迷你 MCP 权限服务（stdio，几十行 Python）挂 `--permission-prompt-tool`
- AstrBot WebSocket 推送 `permission_request` → chat 前端批准卡片（允许/拒绝/记住）→ 决策回流
- 对标 CloudCLI `canUseTool` 源码已研读（`claude-runtime.provider.js:987`：挂起→推送→await 决策→回流，支持"记住选择"动态白名单）

## 4. 组件三：技能同步（软链接方案）

| 环境 | 操作 | 说明 |
|------|------|------|
| 本地 Windows | `mklink /J "%USERPROFILE%\.claude\skills" "D:\tjs\tys\AstrBot\data\skills"` | junction 免管理员；需先清空/备份原目录 |
| 服务器 Linux（二期） | `ln -s /root/apps/yuansheng-astrbot/data/skills ~/.claude/skills` | 容器内 HOME 持久化到卷 |

- 两边技能**格式同构**（目录名=技能名 + SKILL.md + YAML frontmatter），一份文件两个系统读
- 技能页新增/编辑（写 `data/skills/<name>/SKILL.md`）→ claude 引擎**下一条消息**即可用（引擎每请求重建技能清单）；反向在 `~/.claude/skills` 放的技能也出现在 AstrBot 技能页
- 注意：AstrBot 内置技能（builtin_stars）不在 data/skills，不参与同步（如需引入做复制即可）

**场景模板 SKILL.md 化（/场景名 触发的基础）**：把 4 个内置分析场景落盘为 `data/skills/高意向挖掘/SKILL.md` 等（从 `analysis_scenarios.json` 生成，场景编辑保存时同步写）；适配器收到 `/场景名 描述` 开头的消息时确定性改写为技能调用指令（不依赖模型自觉）。数据分析页「开始分析」跳转会话改走 claude 引擎 → **二期**。

## 5. 组件四：部署（二期预案，本期只做本地）

1. 镜像：Dockerfile 加 `npm i -g @anthropic-ai/claude-code`（镜像内已有 Node）+ 数据卷挂 `~/.claude`
2. compose environment 注入 GLM 端点三变量
3. 服务器 `ln -s` 技能目录（见上表）
4. 管理台配置 claude_code 提供商（或直接写 cmd_config.json）
5. 现有 nginx/域名无需变更（就是 dashboard 的 #/chat）
6. 回滚：提供商不选即完全回到现状；镜像可回退

## 6. 分期与验收

**本期（MVP）验收清单（本地）**：
- [ ] 1. chat 选 Claude 引擎 →"分析近7天问过价格的客户"→ agent 真查 data_v4.db（工具调用可见）→ 真实数据报告 → 追问有效
- [ ] 2. `/高意向挖掘 近7天价格` → 场景指令确定性执行
- [ ] 3. 技能页新增技能 → 新会话立即可用
- [ ] 4. 客服机器人回归零影响（微信发消息仍正常小缘回复）
- [ ] 5. `rm -rf xxx` 类被拒且聊天可见拦截提示
- [ ] 6. ruff/构建绿；方案文档与 CUSTOM_DEV_GUIDE §5 登记

**二期**：权限批准卡片（MCP+前端）→ 服务器部署 → 数据分析页跳转引擎化 → 图片输入。

## 7. 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| GLM 对官方复杂工具循环/skills 遵循度低于 Claude 原模 | 长链任务可能半途而废 | 系统提示词收紧步骤；可一键换强模型端点（改 2 个配置）；实测校准 |
| 双份历史（AstrBot 展示副本 + 引擎自管） | 追问依赖 --resume，若 claude 本地会话被清理则失忆 | 映射失效时自动开新引擎会话并在聊天提示"上下文已重置" |
| 长任务（分钟级）与 SSE 心跳 | 前端可能断流 | 复用现有心跳机制；工具执行期间持续发状态行保活 |
| CLI 版本升级改 stream-json 格式 | 解析崩溃 | 锁定安装版本；解析器宽容（未知事件忽略） |
| Windows junction 权限/杀软 | 链接创建失败 | 文档给出手动命令；失败降级为"保存时复制"开关 |
| 引擎误写数据库 | 数据损坏 | deny 规则+只读系统提示+MVP 期间本地库已有备份习惯；二期权限卡片根治 |

## 8. 对现有系统影响面（审计）

| 系统 | 影响 |
|------|------|
| 微信客服机器人（wecom+小缘+转人工） | **零改动**（provider 路由隔离，回归验证项 4） |
| chat 前端 | 零改动（provider 选择器原生兼容） |
| 数据分析功能（场景/导出/昵称） | 零改动；二期可选把跳转会话切到新引擎 |
| AstrBot 管线/核心 | 仅新增 1 适配器文件 + default.py schema 条目 + 1 张映射表（或 sp 键） |
| 服务器 | 本期不动 |

---

### 附：访谈决策记录
1. 复述纠偏：主目的=chat 数据分析 agent 化，非重做 chat
2. 交互形态=自然语言+/场景名 都要（页面跳转引擎化二期）
3. 技能同步=软链接（用户提议）
4. MVP 验收线=本地三链路全通；权限"不允许删除命令即可"
5. 权限卡片/部署=二期预案

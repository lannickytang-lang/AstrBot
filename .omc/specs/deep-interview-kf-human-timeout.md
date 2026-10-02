# Deep Interview Spec: 转人工超时兜底 + 随时人工介入

## Metadata
- Interview ID: di-kf-human-timeout-20261002
- Rounds: 2
- Final Ambiguity Score: 18%
- Type: brownfield（custom_plugins/kf_human_transfer v0.2.x）
- Generated: 2026-10-02
- Threshold: 0.2 / Source: default
- Status: IMPLEMENTED (v0.3.1, 2026-10-02)
- Platform discovery: 95018 = bot proactive send forbidden in KF session states 3 AND 4 (hard rule, not a race) — recovery notice delivered via AI context + owner app notification instead

## 问题（真实场景）
客户发"转人工"→ state=3 人工接待。若店主没回复、或回复几轮后离开且未点企微"结束会话"：
客户后续消息全部落空（AI 静默防抢话），最长 24 小时收不到任何回音。

## 拓扑
| 组件 | 状态 | 说明 |
|------|------|------|
| 未回复超时兜底 | active | 人工会话中客户消息 2 分钟无人工回复 → 自动交还 AI |
| 店主离开未点结束 | active（并入同一计时器） | 计时基准=客户最近一条消息；人工回复即重置 |
| 恢复衔接提示 | active | 交还 AI 时给客户发一条衔接消息 |
| 任意时刻人工介入 | active（用户新增分叉） | AI 接管状态下店主在企微发消息 → 自动切回人工 |

## 方案（状态机 v3）

```
人工中(state=3)：客户消息到达 → 记 last_customer_msg
                 店主消息(origin=5)到达 → 记 last_servicer_msg（重置计时）
  扫描循环(30s)：last_customer_msg > last_servicer_msg
                 且 now - last_customer_msg > 120s
    → kf/service_state/trans 3→4 + 发衔接消息给客户 + 解除人工标记
    → 客户下一条消息由 AI 正常应答（静默黑洞消除）

AI 中(state≠3)：店主 origin=5 消息到达（=店主主动介入）
    → 自动 trans 3（servicer=TangJingShan）+ 标记人工
    → AI 回到静默，店主无缝继续人工对话（无需任何管理台操作）
```

- 衔接消息（配置项 recovery_text，默认）："店主暂时不在，已为您转回智能客服小缘继续为您解答～如您急需，请留言店主上线后会第一时间回复您。"
- 超时时长 human_timeout_seconds 配置项，默认 120
- 24h 总回收逻辑保留不变（兜底的兜底）
- 计时状态持久化在插件 state.json（last_customer_msg/last_servicer_msg per customer），重启安全

## 验收标准
- [ ] 客户在人工会话发消息，2 分钟无人工回复 → state 自动 3→4，客户收到衔接消息，下一条消息 AI 正常回答
- [ ] 店主在 2 分钟内回复（origin=5）→ 计时重置，不触发交还
- [ ] AI 接管状态下店主在企微直接发消息 → state 自动切回 3，AI 静默，客户与店主正常人工对话
- [ ] 店主离开未点结束 + 客户 2 分钟后追问 → 同第一场景，不再永久静默
- [ ] 24h 总回收仍生效
- [ ] 上述全部状态迁移走企微 API 实测

## 实现结果（v0.3.1，deploy 20261002_1148）
- 已上线：3 分钟超时交还/稍等延长 6 分钟/触发即回召唤提示/恢复话术入 AI 上下文/店主应用通知/零操作接管/新客欢迎语
- 实测：trans 3→4 自动触发 ✓、衔接话术入上下文 ✓、message/send 通道 ✓（errcode 0）；待用户手机端全场景回归
- 遗留：欢迎语需新客户实测；95013（会话结束后需客户先发消息才能再转人工）为平台行为

## 非目标
- 不做店主端推送提醒（邮件/企微通知均不做）
- 不改 48h 平台窗口限制（超窗主动发消息平台会拒，属企微规则）
- 不做多接待人路由（始终 TangJingShan）

## 技术落点
- `custom_plugins/kf_human_transfer/main.py`：on_kf_message 记录双时间戳；_reaper_loop 改 30s 扫描+超时交还+衔接消息；origin=5 且 state≠3 → 自动 trans 3
- `_conf_schema.json`：human_timeout_seconds=120、recovery_text
- 插件改动无需重建镜像，scp+重启容器即生效

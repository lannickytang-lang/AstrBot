import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config import AstrBotConfig

# WeChat KF message origin (verified against live traffic):
# 3 = WeChat customer, 5 = servicer (human staff reply), 4 = system event.
# Anything != 3 must never reach the LLM.
ORIGIN_CUSTOMER = 3

# WeChat KF service states (see kf/service_state/get).
STATE_UNHANDLED = 0
STATE_BOT = 1
STATE_QUEUING = 2
STATE_HUMAN = 3
STATE_ENDED = 4

STATE_NAMES = {
    STATE_UNHANDLED: "未处理(新会话)",
    STATE_BOT: "智能助手接待",
    STATE_QUEUING: "待接入池排队",
    STATE_HUMAN: "人工接待中",
    STATE_ENDED: "已结束",
}

HOURS_48 = 48 * 3600


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _origin_role(origin) -> str:
    return "customer" if origin == ORIGIN_CUSTOMER else "servicer"


@register(
    "astrbot_plugin_kf_human_transfer",
    "yuansheng",
    "微信客服转人工：关键词/管理台指令转接、人工期间 AI 静默、防回环、超时自动回收、全量聊天记录（含会话页同步）",
    "0.2.1",
)
class KfHumanTransferPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config if config is not None else {}
        plugin_dir = Path(__file__).parent
        self.state_path = plugin_dir / "state.json"
        self.chat_log_path = plugin_dir / "chat_log.jsonl"
        # customer_id -> last activity unix ts (customer or servicer messages)
        self.last_active: dict[str, float] = {}
        # customer_id -> transferred-to-human unix ts
        self.human_since: dict[str, float] = {}
        # the single KF account in use, captured from incoming messages
        self.open_kfid = ""
        self._reaper_task: asyncio.Task | None = None
        self._backfill_task: asyncio.Task | None = None
        self._load_state()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def initialize(self):
        # backfill chat log from WeChat's 3-day sync archive on first run
        if not self.chat_log_path.exists():
            self._backfill_task = asyncio.create_task(self._backfill_chat_log())
        self._reaper_task = asyncio.create_task(self._reaper_loop())
        logger.info("[kf_human_transfer] initialized")

    async def terminate(self):
        for task in (self._reaper_task, self._backfill_task):
            if task:
                task.cancel()
        self._save_state()

    # ------------------------------------------------------------------
    # config helpers
    # ------------------------------------------------------------------

    @property
    def keywords(self) -> list[str]:
        return [k for k in (self.config.get("keywords") or []) if str(k).strip()]

    @property
    def servicer_userid(self) -> str:
        return str(self.config.get("servicer_userid", "") or "").strip()

    # ------------------------------------------------------------------
    # WeChat KF API helpers (wechatpy client is sync -> run in thread)
    # ------------------------------------------------------------------

    def _get_adapter(self):
        platform = self.context.get_platform("wecom")
        if platform is None or not getattr(platform, "wechat_kf_api", None):
            return None
        return platform

    async def _get_state(self, open_kfid: str, customer_id: str) -> int | None:
        """Query live session state. Returns None when the API call fails."""
        adapter = self._get_adapter()
        if adapter is None:
            return None
        try:
            resp = await asyncio.to_thread(
                adapter.wechat_kf_api.get_service_state,
                open_kfid,
                customer_id,
            )
        except Exception as e:
            logger.warning(f"[kf_human_transfer] get_service_state failed: {e}")
            return None
        if resp.get("errcode", 0) != 0:
            logger.warning(
                f"[kf_human_transfer] get_service_state errcode="
                f"{resp.get('errcode')} {resp.get('errmsg')}"
            )
            return None
        return int(resp.get("service_state", -1))

    async def _trans_state(
        self,
        open_kfid: str,
        customer_id: str,
        target_state: int,
        servicer_userid: str = "",
    ) -> tuple[bool, str]:
        """Transition session to target_state. Returns (ok, message)."""
        adapter = self._get_adapter()
        if adapter is None:
            return False, "wecom 平台未加载"
        try:
            resp = await asyncio.to_thread(
                adapter.wechat_kf_api.trans_service_state,
                open_kfid,
                customer_id,
                target_state,
                servicer_userid,
            )
        except Exception as e:
            return False, f"调用异常: {e}"
        if resp.get("errcode", 0) != 0:
            return False, (f"errcode={resp.get('errcode')} {resp.get('errmsg', '')}")
        return True, "ok"

    async def _resolve_kfid(self) -> str:
        """Resolve the KF account id: last seen from messages, else via API."""
        if self.open_kfid:
            return self.open_kfid
        adapter = self._get_adapter()
        if adapter is None:
            return ""
        kf_name = getattr(adapter, "kf_name", "") or ""
        try:
            resp = await asyncio.to_thread(adapter.wechat_kf_api.get_account_list)
            for acc in resp.get("account_list", []):
                if not kf_name or acc.get("name") == kf_name:
                    self.open_kfid = acc.get("open_kfid", "")
                    break
        except Exception as e:
            logger.warning(f"[kf_human_transfer] resolve kfid failed: {e}")
        return self.open_kfid

    # ------------------------------------------------------------------
    # persistence: tracking state + full chat log
    # ------------------------------------------------------------------

    def _load_state(self):
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.last_active = {
                k: float(v) for k, v in data.get("last_active", {}).items()
            }
            self.human_since = {
                k: float(v) for k, v in data.get("human_since", {}).items()
            }
            self.open_kfid = data.get("open_kfid", "")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"[kf_human_transfer] load state failed: {e}")

    def _save_state(self):
        try:
            self.state_path.write_text(
                json.dumps(
                    {
                        "last_active": self.last_active,
                        "human_since": self.human_since,
                        "open_kfid": self.open_kfid,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[kf_human_transfer] save state failed: {e}")

    def _touch(self, customer_id: str):
        if customer_id:
            self.last_active[customer_id] = time.time()
            self._save_state()

    def _mark_human(self, customer_id: str):
        self.human_since[customer_id] = time.time()
        self._save_state()

    def _unmark_human(self, customer_id: str):
        self.human_since.pop(customer_id, None)
        self._save_state()

    def _append_log(self, customer_id: str, from_role: str, text: str, ts: float):
        """Append one message line to the complete chat log (JSONL)."""
        if not customer_id:
            return
        try:
            line = json.dumps(
                {
                    "ts": int(ts),
                    "time": _iso(ts),
                    "customer_id": customer_id,
                    "from": from_role,
                    "text": text,
                },
                ensure_ascii=False,
            )
            with open(self.chat_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.warning(f"[kf_human_transfer] append chat log failed: {e}")

    async def _append_conv_history(self, customer_id: str, role: str, text: str):
        """Append one message to the customer's AstrBot conversation so the
        dashboard chat-history page shows human-phase records too."""
        if not customer_id:
            return
        umo = f"wecom:FriendMessage:{customer_id}"
        try:
            cm = self.context.conversation_manager
            cid = await cm.get_curr_conversation_id(umo)
            if cid:
                conv = await cm.get_conversation(umo, cid)
                history = json.loads(conv.history) if conv and conv.history else []
            else:
                cid = await cm.new_conversation(umo)
                history = []
            history.append({"role": role, "content": [{"type": "text", "text": text}]})
            await cm.update_conversation(umo, cid, history)
        except Exception as e:
            logger.warning(f"[kf_human_transfer] append conv history failed: {e}")

    async def _backfill_chat_log(self):
        """Seed the chat log from WeChat's sync archive (last 3 days).
        Retries until the wecom platform adapter is available."""
        for _ in range(20):
            adapter = self._get_adapter()
            kfid = self.open_kfid or await self._resolve_kfid()
            if adapter is None or not kfid:
                await asyncio.sleep(30)
                continue
            cursor = ""
            count = 0
            try:
                while True:
                    resp = await asyncio.to_thread(
                        adapter.wechat_kf_api.sync_msg,
                        "",
                        kfid,
                        cursor,
                        1000,
                    )
                    if resp.get("errcode", 0) != 0:
                        logger.warning(
                            f"[kf_human_transfer] backfill sync_msg errcode="
                            f"{resp.get('errcode')} {resp.get('errmsg')}"
                        )
                        return
                    for m in resp.get("msg_list", []):
                        count += 1
                        cid = m.get("external_userid", "")
                        ts = float(m.get("send_time", 0))
                        if m.get("msgtype") == "event":
                            ev = m.get("event", {})
                            text = (
                                f"[事件:{ev.get('event_type', '')}"
                                f"{'/change=' + str(ev.get('change_type')) if ev.get('change_type') else ''}]"
                            )
                            self._append_log(cid, "system", text, ts)
                            continue
                        text = (m.get("text") or {}).get("content", "")
                        if not text:
                            text = f"[{m.get('msgtype', '消息')}]"
                        self._append_log(cid, _origin_role(m.get("origin")), text, ts)
                    if not resp.get("has_more"):
                        break
                    cursor = resp.get("next_cursor", "")
                    if not cursor:
                        break
                logger.info(
                    f"[kf_human_transfer] chat log backfilled with {count} messages"
                )
                return
            except Exception as e:
                logger.warning(f"[kf_human_transfer] backfill failed: {e}")
                await asyncio.sleep(30)

    def _read_log(self, customer_id: str, count: int) -> list[dict]:
        entries = []
        try:
            with open(self.chat_log_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("customer_id") == customer_id:
                        entries.append(d)
        except FileNotFoundError:
            pass
        return entries[-count:]

    # ------------------------------------------------------------------
    # guard: runs on every WeChat KF message before the LLM
    # ------------------------------------------------------------------

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def on_kf_message(self, event: AstrMessageEvent):
        """Gate every WeChat KF message: anti-loopback, anti-hijack,
        keyword-triggered human transfer, and complete chat logging."""
        if event.get_platform_name() != "wecom":
            return
        raw = event.message_obj.raw_message or {}
        if not isinstance(raw, dict):
            return
        customer_id = raw.get("external_userid") or event.get_sender_id()
        origin = raw.get("origin")
        open_kfid = raw.get("open_kfid") or raw.get("OpenKfId") or ""
        if open_kfid:
            self.open_kfid = open_kfid
        self._touch(customer_id)

        # log every message (customer and servicer) with a timestamp
        text = event.message_str.strip() or f"[{raw.get('msgtype', '消息')}]"
        send_time = raw.get("send_time")
        ts = float(send_time) if send_time else time.time()
        self._append_log(customer_id, _origin_role(origin), text, ts)

        # Anti-loopback: servicer replies must never reach the AI, but keep
        # them visible in the dashboard conversation history.
        if origin != ORIGIN_CUSTOMER:
            await self._append_conv_history(customer_id, "assistant", f"[人工] {text}")
            event.stop_event()
            return

        # Anti-hijack: while a human is servicing, the AI stays silent; the
        # customer's message goes to the human and into the history only.
        state = await self._get_state(open_kfid, customer_id)
        if state == STATE_HUMAN:
            await self._append_conv_history(customer_id, "user", text)
            event.stop_event()
            return

        # Keyword-triggered transfer.
        if text and any(kw in text for kw in self.keywords):
            ok, msg = await self._trans_state(
                open_kfid, customer_id, STATE_HUMAN, self.servicer_userid
            )
            if ok:
                self._mark_human(customer_id)
                guide = str(self.config.get("guide_text", ""))
                self._append_log(customer_id, "system", "[触发转人工]", time.time())
                if guide:
                    await self._append_conv_history(
                        customer_id, "assistant", f"[系统] {guide}"
                    )
                    await event.send(MessageChain().message(guide))
            else:
                logger.warning(
                    f"[kf_human_transfer] keyword transfer failed for "
                    f"{customer_id}: {msg}"
                )
            event.stop_event()
            return
        # otherwise: fall through, the AI answers normally

    @filter.on_decorating_result()
    async def on_bot_reply(self, event: AstrMessageEvent):
        """Log every AI reply sent to a WeChat KF customer."""
        if event.get_platform_name() != "wecom":
            return
        result = event.get_result()
        if result is None or not result.chain:
            return
        parts = []
        for comp in result.chain:
            t = getattr(comp, "text", None)
            if t:
                parts.append(str(t))
        text = "".join(parts) or "[媒体消息]"
        self._append_log(event.get_sender_id(), "ai", text, time.time())

    # ------------------------------------------------------------------
    # dashboard commands (admin only)
    # ------------------------------------------------------------------

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("kf列表", alias={"kflist"})
    async def kf_list(self, event: AstrMessageEvent):
        """查看插件跟踪的微信客服客户（ID/模式/最近活跃）"""
        if not self.last_active:
            await event.send(MessageChain().message("（暂无客户互动记录）"))
            return
        now = time.time()
        lines = ["已跟踪的客户："]
        for cid, ts in sorted(
            self.last_active.items(), key=lambda x: x[1], reverse=True
        ):
            mode = "人工" if cid in self.human_since else "AI"
            age = int((now - ts) / 60)
            age_str = f"{age}分钟前" if age < 1440 else f"{age // 1440}天前"
            lines.append(f"- {cid}｜{mode}｜活跃:{age_str}")
        await event.send(MessageChain().message("\n".join(lines)))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("kf记录", alias={"kflog"})
    async def kf_log(self, event: AstrMessageEvent, customer_id: str, count: int = 20):
        """查看某客户完整聊天记录（客户/店主/AI），如: kf记录 wmxxxx 30"""
        entries = self._read_log(customer_id, max(1, min(count, 100)))
        if not entries:
            await event.send(MessageChain().message("该客户暂无聊天记录"))
            return
        who = {"customer": "客户", "servicer": "店主", "ai": "AI", "system": "系统"}
        lines = [f"最近 {len(entries)} 条记录："]
        for d in entries:
            lines.append(
                f"[{d.get('time', '')}] {who.get(d.get('from'), d.get('from'))}: "
                f"{str(d.get('text', ''))[:80]}"
            )
        await event.send(MessageChain().message("\n".join(lines)))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("kf状态", alias={"kfstate"})
    async def kf_status(self, event: AstrMessageEvent, customer_id: str):
        """查询某客户会话状态，如: kf状态 wmxxxx"""
        kfid = await self._resolve_kfid()
        if not kfid:
            await event.send(MessageChain().message("无法解析客服账号ID"))
            return
        state = await self._get_state(kfid, customer_id)
        if state is None:
            await event.send(MessageChain().message("状态查询失败，见日志"))
            return
        now = time.time()
        last = self.last_active.get(customer_id)
        last_str = f"{int((now - last) / 3600)}小时前" if last else "无记录(插件安装前)"
        mode = "人工" if customer_id in self.human_since else "AI"
        await event.send(
            MessageChain().message(
                f"会话状态：{STATE_NAMES.get(state, state)}\n"
                f"插件模式：{mode}｜最近活跃：{last_str}"
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("kf人工", alias={"kfhuman"})
    async def kf_takeover(self, event: AstrMessageEvent, customer_id: str):
        """把某客户会话转给店主人工接待，如: kf人工 wmxxxx"""
        kfid = await self._resolve_kfid()
        if not kfid:
            await event.send(MessageChain().message("无法解析客服账号ID"))
            return
        state = await self._get_state(kfid, customer_id)
        if state == STATE_HUMAN:
            await event.send(
                MessageChain().message("该客户已在人工接待中，请直接在企微回复")
            )
            return
        if state == STATE_ENDED:
            await event.send(
                MessageChain().message("该会话已结束，客户重新发消息后才能转接")
            )
            return
        if not self.servicer_userid:
            await event.send(
                MessageChain().message(
                    "未配置接待人员 userid（插件配置 servicer_userid）"
                )
            )
            return
        # 48h window warning for proactive outreach
        warn = ""
        last = self.last_active.get(customer_id)
        if not last:
            warn = "\n⚠️无互动记录：若客户超48小时未发消息，你主动发消息可能被微信拒发"
        elif time.time() - last > HOURS_48:
            warn = "\n⚠️客户超48小时未互动，你主动发消息可能被微信拒发"
        ok, msg = await self._trans_state(
            kfid, customer_id, STATE_HUMAN, self.servicer_userid
        )
        if ok:
            self._mark_human(customer_id)
            self._append_log(
                customer_id,
                "system",
                f"[店主指令转人工→{self.servicer_userid}]",
                time.time(),
            )
            await event.send(
                MessageChain().message(
                    f"已转给人工（{self.servicer_userid}），请在企微「微信客服」中回复该客户。{warn}"
                )
            )
        else:
            await event.send(MessageChain().message(f"转接失败：{msg}"))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("kf恢复", alias={"kfrecover"})
    async def kf_recover(self, event: AstrMessageEvent, customer_id: str):
        """结束人工会话，客户下次咨询由 AI 接待，如: kf恢复 wmxxxx"""
        kfid = await self._resolve_kfid()
        if not kfid:
            await event.send(MessageChain().message("无法解析客服账号ID"))
            return
        state = await self._get_state(kfid, customer_id)
        if state != STATE_HUMAN:
            await event.send(
                MessageChain().message(
                    f"当前状态为「{STATE_NAMES.get(state, state)}」，无需恢复"
                )
            )
            self._unmark_human(customer_id)
            return
        ok, msg = await self._trans_state(kfid, customer_id, STATE_ENDED)
        if ok:
            self._unmark_human(customer_id)
            self._append_log(
                customer_id, "system", "[结束人工会话→AI接管]", time.time()
            )
            await event.send(
                MessageChain().message("已结束人工会话。客户下次发消息时将由 AI 接待")
            )
        else:
            await event.send(MessageChain().message(f"结束会话失败：{msg}"))

    # ------------------------------------------------------------------
    # background reaper: auto-recover stale human sessions
    # ------------------------------------------------------------------

    async def _reaper_loop(self):
        interval_min = max(5, int(self.config.get("scan_interval_minutes", 30)))
        recover_hours = max(1, int(self.config.get("auto_recover_hours", 24)))
        while True:
            try:
                await asyncio.sleep(interval_min * 60)
                now = time.time()
                stale = [
                    cid
                    for cid, since in self.human_since.items()
                    if now - max(since, self.last_active.get(cid, since))
                    > recover_hours * 3600
                ]
                for cid in stale:
                    kfid = await self._resolve_kfid()
                    if not kfid:
                        break
                    ok, msg = await self._trans_state(kfid, cid, STATE_ENDED)
                    if ok:
                        logger.info(
                            f"[kf_human_transfer] auto-recovered stale human "
                            f"session {cid}"
                        )
                        self._append_log(
                            cid, "system", "[超时自动回收→AI接管]", time.time()
                        )
                        self._unmark_human(cid)
                    else:
                        # session may have already ended or customer left;
                        # stop tracking so the AI is not silenced forever
                        state = await self._get_state(kfid, cid)
                        if state != STATE_HUMAN:
                            self._unmark_human(cid)
                        else:
                            logger.warning(
                                f"[kf_human_transfer] auto-recover failed for "
                                f"{cid}: {msg}, will retry next scan"
                            )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"[kf_human_transfer] reaper error: {e}")

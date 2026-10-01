"""Conversation analysis service for the dashboard data-analysis page.

Provides marketing-oriented scenario prompt templates, filtered conversation
export (CSV/JSONL), and creation of pre-seeded webchat analysis sessions that
run inside the regular chat pipeline with a dedicated analyst persona.
"""

from __future__ import annotations

import asyncio
import csv
import json
import uuid
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.dashboard.services.chat_service import build_webchat_unified_msg_origin

ANALYST_PERSONA_ID = "marketing_analyst"
ANALYST_PERSONA_PROMPT = (
    "你是「缘声琴行」的资深营销分析顾问，拥有 15 年乐器培训行业一线销售与客户增长经验，"
    "精通客户意向分级、到店转化与私域挽回。\n"
    "工作守则：\n"
    "1. 只依据系统注入的客户会话事实进行分析，绝不编造客户没有表达过的信息；\n"
    "2. 关键结论尽量引用客户原话作为依据；\n"
    "3. 输出使用简体中文，结构化呈现（表格 + 要点），跟进话术必须口语化、可直接复制发送；\n"
    "4. 涉及门店业务事实（价格、课程、优惠）时以会话内容与知识库为准，不确定时建议店主人工确认；\n"
    "5. 你的服务对象是店主本人，他需要的是直接可执行的获客与成交动作。"
)

MAX_ANALYSIS_CONVERSATIONS = 50
MAX_MESSAGES_PER_CONVERSATION = 40
MAX_MESSAGE_CHARS = 400
MAX_CORPUS_CHARS = 300_000
MAX_EXPORT_PAGES = 100

DEFAULT_SCENARIOS: list[dict] = [
    {
        "id": "intent",
        "name": "高意向客户挖掘",
        "icon": "🎯",
        "built_in": True,
        "description": (
            "按需求明确度、预算信号、时间紧迫性等维度给每个客户评意向等级"
            "（S/A/B/C），输出按意向排序的客户清单 + 可直接复制的跟进话术。"
        ),
        "instruction": (
            "请逐个分析以上客户会话，按五个维度评估意向：需求明确度、预算信号、"
            "时间紧迫性、决策人身份、到店意愿。输出：\n"
            "1. 按意向排序的客户表格：客户ID / 意向等级(S/A/B/C) / 意向课程或乐器 / "
            "预算与顾虑 / 推荐跟进动作与最佳触达时间\n"
            "2. 为 S、A 级客户各写一句可直接复制发送的微信跟进话术（口语化、带具体钩子，"
            "如团购体验价/到店礼/限时名额）\n"
            "3. 总体判断：本周最优先跟进的 3 个客户及理由\n"
            "评分标准：S=有明确时间或预算信号且互动≥3轮；A=需求明确但无时间信号；"
            "B=泛泛咨询；C=仅一句话且无后续。只依据会话事实，不编造。"
        ),
    },
    {
        "id": "visit",
        "name": "到店转化跟进",
        "icon": "🏪",
        "built_in": True,
        "description": (
            "识别「咨询过但未到店」的客户，结合团购体验课、到店礼等钩子，"
            "为每人产出邀约话术与最佳触达时间。"
        ),
        "instruction": (
            "以上客户均已咨询但尚未到店。请：\n"
            "1. 推断每位客户未到店的原因（价格犹豫/时间未定/对比中/兴趣冷却）\n"
            "2. 输出邀约表格：客户ID / 未到店原因 / 推荐钩子(团购体验课/到店礼/"
            "试课费全退/限时名额) / 最佳触达时间 / 一句可直接复制的邀约话术\n"
            "3. 标注优先级（本周必邀 / 持续培育）\n"
            "话术要口语化、不超过 60 字、带明确行动指令（如「周六上午 10 点我帮您留位」）。"
        ),
    },
    {
        "id": "winback",
        "name": "流失预警挽回",
        "icon": "💤",
        "built_in": True,
        "description": (
            "找出有过意向信号但已冷却的客户，输出挽回优先级排序与开场话术"
            "（新优惠 / 新课程 / 关怀切入）。"
        ),
        "instruction": (
            "以上客户曾表现出兴趣但已冷却。请：\n"
            "1. 按挽回价值排序输出表格：客户ID / 当时意向 / 挽回优先级 / "
            "推荐切入角度(新优惠/新课程/限时活动/关怀问候)\n"
            "2. 为前 5 位客户各写一条挽回开场白（自然不硬销，先给价值再提行动）\n"
            "3. 指出哪些客户不值得再花精力（如仅问一句即走且无兴趣信号），并说明理由。"
        ),
    },
    {
        "id": "insight",
        "name": "经营洞察报告",
        "icon": "📈",
        "built_in": True,
        "description": (
            "不针对单个客户：统计咨询热点、价格异议归类、转化漏斗与知识库缺口，"
            "输出经营改进建议报告。"
        ),
        "instruction": (
            "不针对单个客户，请输出一份经营洞察报告：\n"
            "1. 咨询热点 TOP5（课程/乐器及占比）\n"
            "2. 价格异议归类：客户在价格上的典型顾虑及占比，给出应对话术建议\n"
            "3. 转化漏斗：咨询 → 深聊(≥3轮) → 留时间线索 → 表达到店意愿，"
            "各阶段数量与流失率\n"
            "4. 机器人应答质量抽查：哪些问题机器人没答好或答偏（附客户ID），"
            "建议补充进知识库\n"
            "5. 本周行动建议：最多 5 条，按预期效果排序。"
        ),
    },
]


class AnalysisServiceError(Exception):
    pass


class AnalysisService:
    def __init__(
        self,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        self.db_helper = db_helper
        self.conv_mgr = core_lifecycle.conversation_manager
        self.persona_mgr = core_lifecycle.persona_mgr
        self.core_lifecycle = core_lifecycle
        self.scenario_file = Path(get_astrbot_data_path()) / "analysis_scenarios.json"

    # ------------------------------------------------------------------
    # Customer nickname resolution (WeChat Work kf/customer/batchget)
    # ------------------------------------------------------------------

    def _get_wechat_kf_api(self):
        """Return the WeChat KF API wrapper from the running wecom adapter."""
        for inst in self.core_lifecycle.platform_manager.get_insts():
            api = getattr(inst, "wechat_kf_api", None)
            if api is not None:
                return api
        return None

    async def resolve_customer_names(
        self,
        customer_ids: list[str],
        backfill: bool = True,
    ) -> dict:
        """Resolve WeChat nicknames/avatars for external customer IDs.

        The ``kf_customer_profile`` table is the single source: profiles are
        written once (either by the kf plugin on first contact or by the
        backfill below) and every later read is table-only. Missing profiles
        are fetched once via kf/customer/batchget and upserted; failures are
        logged and never block the caller.

        Args:
            customer_ids: External customer IDs (wmQcA1... style).
            backfill: Whether missing profiles may be fetched from the API.

        Returns:
            Mapping from customer ID to ``{"nickname", "avatar"}``. IDs that
            cannot be resolved are absent from the result.
        """
        wanted = [cid for cid in dict.fromkeys(customer_ids) if cid]
        if not wanted:
            return {}

        profiles = {
            p.customer_id: {"nickname": p.nickname, "avatar": p.avatar}
            for p in await self.db_helper.get_kf_customer_profiles(wanted)
        }
        missing = [cid for cid in wanted if cid not in profiles]
        if not missing or not backfill:
            return profiles

        api = self._get_wechat_kf_api()
        if api is None:
            logger.warning(
                "Customer name backfill skipped: wecom platform not running",
            )
            return profiles
        for start in range(0, len(missing), 50):
            chunk = missing[start : start + 50]
            try:
                resp = await asyncio.to_thread(api.batchget_customer, chunk)
            except Exception as exc:
                logger.warning(f"Failed to resolve customer names: {exc}")
                break
            for item in resp.get("customer_list", []) or []:
                cid = item.get("external_userid")
                # WeChat KF returns nickname/avatar at the item top level
                # (older docs show a customer_info wrapper; keep the fallback).
                info = item.get("customer_info") or {}
                corp = (info.get("corporation_info") or {}).get("corp_name", "")
                nickname = item.get("nickname") or info.get("nickname") or corp or ""
                avatar = item.get("avatar") or info.get("avatar") or ""
                if not cid:
                    continue
                try:
                    await self.db_helper.upsert_kf_customer_profile(
                        cid,
                        nickname,
                        avatar,
                    )
                    profiles[cid] = {"nickname": nickname, "avatar": avatar}
                except Exception as exc:
                    logger.warning(
                        f"Failed to store customer profile {cid}: {exc}",
                    )
        return profiles

    # ------------------------------------------------------------------
    # Scenario prompt templates
    # ------------------------------------------------------------------

    def _ensure_scenario_file(self) -> None:
        if not self.scenario_file.exists():
            self._write_scenarios(DEFAULT_SCENARIOS)

    def _read_scenarios(self) -> list[dict]:
        self._ensure_scenario_file()
        try:
            data = json.loads(self.scenario_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(f"Failed to read analysis scenarios: {exc}")
            return [dict(s) for s in DEFAULT_SCENARIOS]
        scenarios = data.get("scenarios") if isinstance(data, dict) else None
        return scenarios if isinstance(scenarios, list) else []

    def _write_scenarios(self, scenarios: list[dict]) -> None:
        self.scenario_file.parent.mkdir(parents=True, exist_ok=True)
        self.scenario_file.write_text(
            json.dumps(
                {"version": 1, "scenarios": scenarios},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    async def list_scenarios(self) -> list[dict]:
        return self._read_scenarios()

    async def create_scenario(self, payload: dict) -> dict:
        name = str(payload.get("name") or "").strip()
        instruction = str(payload.get("instruction") or "").strip()
        if not name or not instruction:
            raise AnalysisServiceError("场景名称与指令内容不能为空")
        scenario = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "icon": str(payload.get("icon") or "✏️").strip() or "✏️",
            "built_in": False,
            "description": str(payload.get("description") or "").strip(),
            "instruction": instruction,
        }
        scenarios = self._read_scenarios()
        scenarios.append(scenario)
        self._write_scenarios(scenarios)
        return scenario

    async def update_scenario(self, scenario_id: str, payload: dict) -> dict:
        scenarios = self._read_scenarios()
        scenario = next((s for s in scenarios if s.get("id") == scenario_id), None)
        if not scenario:
            raise AnalysisServiceError("分析场景不存在")
        for key in ("name", "icon", "description", "instruction"):
            if key in payload and payload[key] is not None:
                value = str(payload[key]).strip()
                if key in ("name", "instruction") and not value:
                    raise AnalysisServiceError(f"{key} 不能为空")
                scenario[key] = value
        self._write_scenarios(scenarios)
        return scenario

    async def restore_scenario(self, scenario_id: str) -> dict:
        default = next((s for s in DEFAULT_SCENARIOS if s["id"] == scenario_id), None)
        if not default:
            raise AnalysisServiceError("仅内置场景支持恢复默认")
        scenarios = self._read_scenarios()
        scenario = next((s for s in scenarios if s.get("id") == scenario_id), None)
        if not scenario:
            raise AnalysisServiceError("分析场景不存在")
        scenario.update(
            {
                "name": default["name"],
                "icon": default["icon"],
                "description": default["description"],
                "instruction": default["instruction"],
                "built_in": True,
            }
        )
        self._write_scenarios(scenarios)
        return scenario

    async def delete_scenario(self, scenario_id: str) -> dict:
        scenarios = self._read_scenarios()
        scenario = next((s for s in scenarios if s.get("id") == scenario_id), None)
        if not scenario:
            raise AnalysisServiceError("分析场景不存在")
        if scenario.get("built_in"):
            raise AnalysisServiceError("内置场景不可删除，可另存副本后修改")
        self._write_scenarios([s for s in scenarios if s.get("id") != scenario_id])
        return {"message": "场景已删除"}

    # ------------------------------------------------------------------
    # Filter parsing
    # ------------------------------------------------------------------

    def _parse_filter(self, payload: dict) -> dict:
        platforms = payload.get("platforms")
        message_types = payload.get("message_types")

        def _clean(value) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(v).strip() for v in value if str(v).strip()]

        return {
            "platforms": _clean(platforms) or ["wecom"],
            "message_types": _clean(message_types) or ["FriendMessage"],
            "keyword_query": str(payload.get("keyword") or "").strip(),
            "created_after": payload.get("created_after"),
            "created_before": payload.get("created_before"),
        }

    async def _fetch_conversations(
        self,
        filter_: dict,
        explicit_conversations: list[dict] | None,
        limit: int,
        page_size: int = 50,
    ) -> list:
        if explicit_conversations:
            conversations = []
            for ref in explicit_conversations[:limit]:
                user_id = str(ref.get("user_id") or "")
                cid = str(ref.get("cid") or "")
                if not user_id or not cid:
                    continue
                conv = await self.conv_mgr.get_conversation(
                    unified_msg_origin=user_id,
                    conversation_id=cid,
                )
                if conv:
                    conversations.append(conv)
            return [
                conv for conv in conversations if conv.persona_id != ANALYST_PERSONA_ID
            ]

        conversations = []
        page = 1
        raw_count = 0
        while page <= MAX_EXPORT_PAGES and len(conversations) < limit:
            batch, total = await self.conv_mgr.get_filtered_conversations(
                page=page,
                page_size=page_size,
                include_history=True,
                created_after=filter_["created_after"],
                created_before=filter_["created_before"],
                platforms=filter_["platforms"],
                message_types=filter_["message_types"],
                keyword_query=filter_["keyword_query"],
            )
            raw_count += len(batch)
            # Exclude prior analysis sessions so they never leak back into
            # the corpus as if they were customer conversations.
            conversations.extend(
                conv for conv in batch if conv.persona_id != ANALYST_PERSONA_ID
            )
            if raw_count >= total or not batch:
                break
            page += 1
        return conversations[:limit]

    # ------------------------------------------------------------------
    # Analysis session creation
    # ------------------------------------------------------------------

    async def _ensure_analyst_persona(self) -> None:
        # get_persona raises ValueError when the persona is missing.
        try:
            await self.persona_mgr.get_persona(ANALYST_PERSONA_ID)
        except ValueError:
            await self.persona_mgr.create_persona(
                persona_id=ANALYST_PERSONA_ID,
                system_prompt=ANALYST_PERSONA_PROMPT,
                tools=[],
            )

    async def create_analysis_session(self, username: str, payload: dict) -> dict:
        """Create a webchat session pre-seeded with filtered conversation corpus.

        The corpus is injected into the LLM context layer only; the display
        layer receives a single summary card so the chat UI stays clean.

        Args:
            username: Dashboard username that will own the chat session.
            payload: Filter fields plus ``scenario_id``.

        Returns:
            Session identifiers, corpus stats and the scenario opening
            instruction for the frontend to auto-send.
        """
        scenario_id = str(payload.get("scenario_id") or "intent")
        scenario = next(
            (s for s in await self.list_scenarios() if s.get("id") == scenario_id),
            None,
        )
        if not scenario:
            raise AnalysisServiceError("分析场景不存在")

        filter_ = self._parse_filter(payload)
        conversations = await self._fetch_conversations(
            filter_,
            payload.get("conversations"),
            MAX_ANALYSIS_CONVERSATIONS,
        )
        if not conversations:
            raise AnalysisServiceError("筛选结果为空，请调整筛选条件后重试")

        customer_ids = [self._customer_id_of(conv.user_id) for conv in conversations]
        names = await self.resolve_customer_names(customer_ids)
        corpus, used_count, truncated = self._build_corpus(conversations, names)
        if not corpus.strip():
            raise AnalysisServiceError("所选会话没有可分析的消息内容")

        await self._ensure_analyst_persona()

        session = await self.db_helper.create_platform_session(
            creator=username,
            platform_id="webchat",
            display_name=f"AI分析 · {scenario['icon']} {scenario['name']}",
        )
        umo = build_webchat_unified_msg_origin(session)
        history = [
            {"role": "user", "content": corpus},
            {
                "role": "assistant",
                "content": (
                    f"已完整读取 {used_count} 个客户会话语料，"
                    "我已建立整体印象。请发送本次分析目标，"
                    "或直接发送预设场景指令开始分析。"
                ),
            },
        ]
        conversation_id = await self.conv_mgr.new_conversation(
            unified_msg_origin=umo,
            platform_id="webchat",
            content=history,
            persona_id=ANALYST_PERSONA_ID,
        )
        summary = self._summary_text(scenario, filter_, used_count, truncated)
        await self.db_helper.insert_platform_message_history(
            platform_id="webchat",
            user_id=session.session_id,
            content={"type": "bot", "message": [{"type": "plain", "text": summary}]},
        )
        return {
            "session_id": session.session_id,
            "conversation_id": conversation_id,
            "conversation_count": used_count,
            "truncated": truncated,
            "opening_instruction": scenario["instruction"],
            "scenario_name": scenario["name"],
        }

    def _build_corpus(
        self,
        conversations: list,
        names: dict | None = None,
    ) -> tuple[str, int, bool]:
        """Render conversations into a compact text corpus for the LLM.

        Args:
            conversations: Conversation objects with history JSON.
            names: Mapping from customer ID to resolved nickname/avatar info.

        Returns:
            Tuple of (corpus text, number of conversations included, whether
            the corpus hit the global character limit).
        """
        names = names or {}
        blocks: list[str] = []
        used_count = 0
        truncated = False
        total_chars = 0
        for index, conv in enumerate(conversations, start=1):
            try:
                messages = json.loads(conv.history) or []
            except (json.JSONDecodeError, TypeError):
                continue
            lines: list[str] = []
            for message in messages[-MAX_MESSAGES_PER_CONVERSATION:]:
                role = message.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = self._extract_text(message.get("content"))
                # System reminders may be appended to user messages; strip
                # everything from the first injected marker onward.
                if "<system" in text:
                    text = text.split("<system", 1)[0].strip()
                if not text:
                    continue
                if len(text) > MAX_MESSAGE_CHARS:
                    text = text[:MAX_MESSAGE_CHARS] + "…"
                lines.append(f"客户: {text}" if role == "user" else f"客服: {text}")
            if not lines:
                continue
            customer_id = self._customer_id_of(conv.user_id)
            nickname = (names.get(customer_id) or {}).get("nickname") or ""
            header_line = f"【客户会话 {index}】客户ID: {customer_id}"
            if nickname:
                header_line += f"（微信昵称：{nickname}）"
            block = header_line + "\n" + "\n".join(lines)
            if total_chars + len(block) > MAX_CORPUS_CHARS:
                truncated = True
                break
            blocks.append(block)
            total_chars += len(block)
            used_count += 1
        header = (
            f"以下是 {used_count} 个客户与智能客服的近期会话记录，"
            "每段以客户ID和微信昵称标识。跟进建议中请同时给出客户ID与昵称，"
            "方便店主识别并人工联系。请基于这些事实进行分析。\n\n"
        )
        return header + "\n\n".join(blocks), used_count, truncated

    @staticmethod
    def _extract_text(content) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") in ("text", "plain"):
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts).strip()
        return ""

    @staticmethod
    def _customer_id_of(user_id: str | None) -> str:
        umo = user_id or ""
        tail = umo.rsplit(":", 1)[-1]
        if "!" in tail:
            tail = tail.rsplit("!", 1)[-1]
        return tail or umo

    def _summary_text(
        self,
        scenario: dict,
        filter_: dict,
        used_count: int,
        truncated: bool,
    ) -> str:
        parts = [f"📊 已载入 {used_count} 个客户会话"]
        conditions = []
        if filter_["platforms"]:
            conditions.append("平台 " + "、".join(filter_["platforms"]))
        if filter_["keyword_query"]:
            conditions.append(f"关键词“{filter_['keyword_query']}”")
        if filter_["created_after"] or filter_["created_before"]:

            def _fmt_date(ts) -> str:
                return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d")

            start = (
                _fmt_date(filter_["created_after"]) if filter_["created_after"] else "…"
            )
            end = (
                _fmt_date(filter_["created_before"])
                if filter_["created_before"]
                else "…"
            )
            conditions.append(f"时间 {start} ~ {end}")
        if conditions:
            parts.append("｜".join(conditions))
        parts.append(f"场景：{scenario['icon']} {scenario['name']}")
        if truncated:
            parts.append("⚠️ 会话数量超出单次分析上限，仅载入最近的部分")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Filtered export
    # ------------------------------------------------------------------

    async def export_by_filter(self, payload: dict) -> tuple[str, BytesIO]:
        """Export conversations matching a filter as CSV or JSONL.

        Args:
            payload: Filter fields plus ``format`` (``csv`` or ``jsonl``).

        Returns:
            Tuple of (filename, file bytes ready for streaming).
        """
        file_format = str(payload.get("format") or "csv").lower()
        if file_format not in ("csv", "jsonl"):
            raise AnalysisServiceError("导出格式仅支持 csv 或 jsonl")

        filter_ = self._parse_filter(payload)
        conversations = await self._fetch_conversations(
            filter_,
            payload.get("conversations"),
            limit=MAX_EXPORT_PAGES * 50,
            page_size=100,
        )
        if not conversations:
            raise AnalysisServiceError("筛选结果为空，没有可导出的会话")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        names = await self.resolve_customer_names(
            [self._customer_id_of(conv.user_id) for conv in conversations],
        )
        if file_format == "jsonl":
            return self._export_jsonl(conversations, timestamp, names)
        return self._export_csv(conversations, timestamp, names)

    def _export_jsonl(
        self,
        conversations: list,
        timestamp: str,
        names: dict,
    ) -> tuple[str, BytesIO]:
        lines = []
        for conv in conversations:
            try:
                content = json.loads(conv.history)
            except (json.JSONDecodeError, TypeError):
                content = []
            customer_id = self._customer_id_of(conv.user_id)
            record = {
                "cid": conv.cid,
                "user_id": conv.user_id,
                "customer_id": customer_id,
                "customer_name": (names.get(customer_id) or {}).get("nickname") or "",
                "platform_id": conv.platform_id,
                "title": conv.title or None,
                "persona_id": conv.persona_id,
                "created_at": conv.created_at,
                "updated_at": conv.updated_at,
                "content": content,
            }
            lines.append(json.dumps(record, ensure_ascii=False))
        file_obj = BytesIO("\n".join(lines).encode("utf-8"))
        return f"astrbot_analysis_export_{timestamp}.jsonl", file_obj

    def _export_csv(
        self,
        conversations: list,
        timestamp: str,
        names: dict,
    ) -> tuple[str, BytesIO]:
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["客户ID", "微信昵称", "平台", "会话ID", "标题", "时间", "角色", "内容"],
        )
        for conv in conversations:
            try:
                messages = json.loads(conv.history) or []
            except (json.JSONDecodeError, TypeError):
                continue
            customer_id = self._customer_id_of(conv.user_id)
            nickname = (names.get(customer_id) or {}).get("nickname") or ""
            created = (
                datetime.fromtimestamp(conv.created_at).strftime("%Y-%m-%d %H:%M:%S")
                if conv.created_at
                else ""
            )
            for message in messages:
                role = message.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = self._extract_text(message.get("content"))
                if "<system" in text:
                    text = text.split("<system", 1)[0].strip()
                if not text:
                    continue
                writer.writerow(
                    [
                        customer_id,
                        nickname,
                        conv.platform_id,
                        conv.cid,
                        conv.title or "",
                        created,
                        "客户" if role == "user" else "客服",
                        text.replace("\n", "\\n"),
                    ]
                )
        file_obj = BytesIO("\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8"))
        return f"astrbot_analysis_export_{timestamp}.csv", file_obj

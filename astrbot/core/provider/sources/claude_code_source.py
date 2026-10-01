"""Claude Code engine provider: bridges the official headless Claude CLI.

Spawns ``claude -p --output-format stream-json`` for each message and maps
AstrBot conversations to native Claude Code sessions (``--resume``), so
memory, context compaction, skills and the tool loop are all handled by the
official engine. The model backend is whatever the local CLI is configured
with (e.g. a DeepSeek/GLM compatible endpoint); optional ``base_url`` /
``api_key`` / ``model`` provider settings override it per deployment.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import astrbot.core.message.components as Comp
from astrbot.core import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.provider import Provider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

DEFAULT_DENY_RULES = [
    "Bash(rm:*)",
    "Bash(rm -rf:*)",
    "Bash(del:*)",
    "Bash(rmdir:*)",
    "Bash(rd:*)",
    "Bash(mkfs*)",
    "Bash(dd:*)",
    "Bash(format:*)",
    "Bash(shred:*)",
]

DEFAULT_SYSTEM_PROMPT = (
    "你是「缘声琴行」店主本人的数据分析助手，运行在管理台聊天里。"
    "工作目录的 CLAUDE.md 写明了客户数据的获取方式（本机 API + 已配置的 API Key），"
    "分析前先读它，用 curl 实际取数，引用真实数字。"
    "如果数据源不存在或为空，用 1-2 条命令快速确认后立即说明并停止，不要深度取证。"
    "删除类命令会被系统拦截（需要审批，当前版本自动拒绝）。"
    "用简体中文回复，报告要结构化、结论可执行。"
)


@register_provider_adapter(
    "claude_code",
    "Claude Code 引擎（官方 CLI 无头模式）",
)
class ClaudeCodeProvider(Provider):
    """Bridge provider that drives the official Claude Code CLI."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.cli_path = str(provider_config.get("cli_path") or "claude")
        self.agent_cwd = str(provider_config.get("cwd") or get_astrbot_data_path())
        self.timeout = int(provider_config.get("timeout") or 900)
        # strict: unlisted tools auto-deny; open (default): bypass + deny-list only.
        self.strict_mode = (
            str(provider_config.get("permission_mode") or "open").lower() == "strict"
        )
        self.model = str(provider_config.get("model") or "").strip() or None
        self.enable_stream = provider_settings.get("enable_stream", True)
        deny_rules = provider_config.get("deny_rules") or DEFAULT_DENY_RULES
        if isinstance(deny_rules, str):
            deny_rules = [deny_rules]
        self.disallowed_tools = [str(rule) for rule in deny_rules if str(rule).strip()]
        self.extra_system_prompt = str(
            provider_config.get("system_prompt") or ""
        ).strip()
        # Optional endpoint overrides. Empty means "inherit the local CLI
        # configuration" (the recommended default: the CLI owns auth/model).
        self.env_overrides: dict[str, str] = {}
        for env_key, cfg_key in (
            ("ANTHROPIC_BASE_URL", "base_url"),
            ("ANTHROPIC_AUTH_TOKEN", "api_key"),
        ):
            value = str(provider_config.get(cfg_key) or "").strip()
            if value:
                self.env_overrides[env_key] = value
        self.session_map_file = (
            Path(get_astrbot_data_path()) / "claude_session_map.json"
        )

    # ------------------------------------------------------------------
    # Session mapping: AstrBot conversation id -> native Claude session id
    # ------------------------------------------------------------------

    def _load_session_map(self) -> dict:
        try:
            data = json.loads(self.session_map_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_session_map(self, mapping: dict) -> None:
        try:
            self.session_map_file.parent.mkdir(parents=True, exist_ok=True)
            self.session_map_file.write_text(
                json.dumps(mapping, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"[claude_code] Failed to save session map: {exc}")

    def _drop_session(self, conversation_id: str | None) -> None:
        if not conversation_id:
            return
        mapping = self._load_session_map()
        if mapping.pop(conversation_id, None) is not None:
            self._save_session_map(mapping)

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _latest_user_text(prompt: str | None, contexts) -> str:
        """Return the newest user message from prompt or contexts.

        Context items may be dicts (persisted history) or pydantic Message
        objects (in-flight runner messages), so both shapes are handled.
        """
        if prompt and str(prompt).strip():
            return str(prompt).strip()
        if isinstance(contexts, list):
            for item in reversed(contexts):
                if isinstance(item, dict):
                    role = item.get("role")
                    content = item.get("content")
                else:
                    role = getattr(item, "role", None)
                    content = getattr(item, "content", None)
                if role != "user":
                    continue
                if isinstance(content, str) and content.strip():
                    return content.strip()
                if isinstance(content, list):
                    texts = []
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                texts.append(str(part.get("text") or ""))
                        elif getattr(part, "type", None) == "text":
                            texts.append(str(getattr(part, "text", "") or ""))
                    text = "\n".join(t for t in texts if t).strip()
                    if text:
                        return text
        return ""

    def _load_scenarios(self) -> list[dict]:
        scenario_file = Path(get_astrbot_data_path()) / "analysis_scenarios.json"
        try:
            data = json.loads(scenario_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        scenarios = data.get("scenarios") if isinstance(data, dict) else None
        return scenarios if isinstance(scenarios, list) else []

    def _match_scenario(self, message: str) -> tuple[dict | None, str]:
        """Match a leading ``/scenario-name`` and return (scenario, rest)."""
        if not message.startswith("/"):
            return None, message
        head, _, rest = message[1:].partition(" ")
        head = head.strip()
        if not head:
            return None, message
        for scenario in self._load_scenarios():
            if head in (str(scenario.get("name")), str(scenario.get("id"))):
                return scenario, rest.strip()
        return None, message

    def _build_system_prompt(self, scenario: dict | None) -> str:
        parts = [DEFAULT_SYSTEM_PROMPT]
        if self.extra_system_prompt:
            parts.append(self.extra_system_prompt)
        if scenario:
            parts.append(
                f"本次任务必须严格按以下场景指令执行：\n{scenario.get('instruction', '')}"
            )
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Command construction
    # ------------------------------------------------------------------

    def _build_command(
        self,
        message: str,
        claude_session_id: str | None,
        scenario: dict | None,
    ) -> list[str]:
        command = [
            self.cli_path,
            "-p",
            message,
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if self.strict_mode:
            # Strict: unlisted tools auto-deny (nothing can prompt in -p mode).
            command += ["--permission-prompts", "none"]
        else:
            # Open (default): allow everything except the deny list. The
            # disallowed list stays effective under bypass mode.
            command += ["--dangerously-skip-permissions"]
        if claude_session_id:
            command += ["--resume", claude_session_id]
        for rule in self.disallowed_tools:
            command += ["--disallowed-tools", rule]
        system_prompt = self._build_system_prompt(scenario)
        if system_prompt:
            command += ["--append-system-prompt", system_prompt]
        if self.model:
            command += ["--model", self.model]
        return command

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _run_engine(
        self,
        message: str,
        conversation_id: str | None,
        scenario: dict | None,
        abort_signal=None,
    ) -> AsyncGenerator[LLMResponse, None]:
        mapping = self._load_session_map()
        claude_session_id = mapping.get(conversation_id) if conversation_id else None
        command = self._build_command(message, claude_session_id, scenario)
        env = {**os.environ, **self.env_overrides}
        logger.info(
            f"[claude_code] spawn: session={claude_session_id or 'new'} "
            f"chars={len(message)} scenario={bool(scenario)}"
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.agent_cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            raise Exception(
                f"未找到 claude CLI（{self.cli_path}）。"
                "请安装：npm install -g @anthropic-ai/claude-code"
            )

        captured_session_id: str | None = None
        full_text_parts: list[str] = []
        final_text: str | None = None
        result_is_error = False

        async def _pump_stderr():
            if proc.stderr is None:
                return
            try:
                async for raw in proc.stderr:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        logger.debug(f"[claude_code][stderr] {line}")
            except Exception:
                pass

        stderr_task = asyncio.create_task(_pump_stderr())
        timed_out = False
        try:
            stdout_task = asyncio.create_task(self._pump_stdout(proc))
            done, _pending = await asyncio.wait(
                [stdout_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=self.timeout,
            )
            if stdout_task not in done:
                timed_out = True
                proc.kill()
                await proc.wait()
            else:
                # stdout EOF means the engine closed its output; reap it.
                await proc.wait()
            (
                captured_session_id,
                full_text_parts,
                final_text,
                result_is_error,
            ) = stdout_task.result()
        except asyncio.CancelledError:
            # Caller cancelled the stream (e.g. stop button): kill the engine.
            if proc.returncode is None:
                proc.kill()
            raise
        finally:
            stderr_task.cancel()

        if timed_out:
            raise Exception(
                f"claude 引擎执行超时（>{self.timeout}s），已终止。可稍后重试。"
            )
        # A stale resume target fails the whole run; fall back to a fresh
        # engine session once so the conversation keeps working.
        if (
            result_is_error
            and claude_session_id
            and not full_text_parts
            and not final_text
        ):
            logger.warning("[claude_code] resume failed; retrying with a fresh session")
            self._drop_session(conversation_id)
            async for response in self._run_engine(
                message, None, scenario, abort_signal
            ):
                yield response
            return

        if captured_session_id and conversation_id:
            mapping = self._load_session_map()
            mapping[conversation_id] = captured_session_id
            self._save_session_map(mapping)

        if final_text is None and full_text_parts:
            final_text = "".join(full_text_parts).strip()
        text = (final_text or "").strip()
        if not text:
            text = "（Claude 引擎未返回文本内容）"

        # Emit the full text as one streaming chunk so the webchat SSE layer
        # produces a `plain` event (the UI renders text from chunks only).
        chunk = LLMResponse("assistant", is_chunk=True)
        chunk.completion_text = text
        chunk.result_chain = MessageChain(chain=[Comp.Plain(text)])
        yield chunk

        response = LLMResponse("assistant")
        response.completion_text = text
        response.result_chain = MessageChain().message(text)
        yield response

    async def _pump_stdout(self, proc):
        """Parse stream-json lines; returns (session_id, text_parts, final, errored)."""
        session_id: str | None = None
        text_parts: list[str] = []
        final_text: str | None = None
        result_is_error = False
        if proc.stdout is None:
            return session_id, text_parts, final_text, result_is_error
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"[claude_code] non-json line: {line[:120]}")
                continue
            event_type = event.get("type")
            if event_type == "system" and event.get("session_id"):
                session_id = event["session_id"]
                continue
            if event_type == "assistant":
                message = event.get("message") or {}
                for block in message.get("content", []) or []:
                    block_type = block.get("type")
                    if block_type == "text":
                        text = block.get("text") or ""
                        if text:
                            text_parts.append(text)
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "tool")
                        summary = self._tool_summary(tool_name, block.get("input"))
                        line_out = f"🔧 执行工具：{tool_name} {summary}".rstrip()
                        logger.info(f"[claude_code] {line_out}")
            elif event_type == "result":
                final_text = str(event.get("result") or "").strip() or None
                if event.get("is_error"):
                    logger.error(
                        "[claude_code] engine result error: "
                        f"{event.get('subtype')} "
                        f"{str(event.get('result'))[:200]}"
                    )
                    result_is_error = True
        return session_id, text_parts, final_text, result_is_error

    @staticmethod
    def _tool_summary(tool_name: str, tool_input) -> str:
        if not isinstance(tool_input, dict):
            return ""
        for key in ("command", "file_path", "pattern", "path", "description"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip().replace("\n", " ")
                return f"· {text[:80]}" + ("…" if len(text) > 80 else "")
        return ""

    # ------------------------------------------------------------------
    # Provider interface
    # ------------------------------------------------------------------

    async def text_chat_stream(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        audio_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        tool_choice: str = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> AsyncGenerator[LLMResponse, None]:
        conversation_id = kwargs.pop("conversation_id", None)
        abort_signal = kwargs.pop("abort_signal", None)
        message = self._latest_user_text(prompt, contexts)
        if not message:
            raise Exception("claude_code 提供商未收到任何用户消息内容")
        if message.split("<system", 1)[0].strip() == "/help":
            # Local answer, no engine spawn.
            scenarios = self._load_scenarios()
            lines = [
                "可用命令：",
                "",
                "/help — 显示本帮助",
                "/clear — 开启新会话（输入框处理）",
            ]
            lines += [
                f"/{s.get('name')} — {s.get('description') or s.get('name')}"
                for s in scenarios
            ]
            lines += [
                "",
                "提示：分析类问题可直接用自然语言描述（按工作目录 CLAUDE.md 的指南调接口取数）。",
                "删除类命令会被系统拦截。",
            ]
            text = "\n".join(lines)
            chunk = LLMResponse("assistant", is_chunk=True)
            chunk.completion_text = text
            chunk.result_chain = MessageChain(chain=[Comp.Plain(text)])
            yield chunk
            response = LLMResponse("assistant")
            response.completion_text = text
            response.result_chain = MessageChain().message(text)
            yield response
            return
        scenario, rest = self._match_scenario(message)
        if scenario:
            scope = rest or "（用户未补充范围，按场景默认执行）"
            message = (
                f"场景「{scenario.get('name')}」被触发。场景指令见系统提示词。"
                f"本次分析范围：{scope}"
            )
        async for response in self._run_engine(
            message, conversation_id, scenario, abort_signal
        ):
            yield response

    async def text_chat(
        self,
        prompt=None,
        session_id=None,
        image_urls=None,
        audio_urls=None,
        func_tool=None,
        contexts=None,
        system_prompt=None,
        tool_calls_result=None,
        model=None,
        extra_user_content_parts=None,
        tool_choice: str = "auto",
        request_max_retries: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        final: LLMResponse | None = None
        async for response in self.text_chat_stream(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            audio_urls=audio_urls,
            func_tool=func_tool,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            model=model,
            tool_choice=tool_choice,
            request_max_retries=request_max_retries,
            **kwargs,
        ):
            final = response
        if final is None:
            raise Exception("claude 引擎未返回任何结果")
        return final

    # ------------------------------------------------------------------
    # Minimal credential plumbing (the CLI owns real auth)
    # ------------------------------------------------------------------

    def get_current_key(self) -> str:
        return str(self.provider_config.get("api_key") or "cli-managed")

    def set_key(self, key: str) -> None:
        self.provider_config["api_key"] = key
        value = str(key or "").strip()
        if value:
            self.env_overrides["ANTHROPIC_AUTH_TOKEN"] = value
        else:
            self.env_overrides.pop("ANTHROPIC_AUTH_TOKEN", None)

    async def get_models(self) -> list[str]:
        model = self.model or "default (inherits local CLI config)"
        return [str(model)]

    async def terminate(self) -> None:
        return None

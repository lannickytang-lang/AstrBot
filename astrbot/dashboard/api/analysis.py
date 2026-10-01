"""Dashboard routes for the conversation analysis feature."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from astrbot.core import logger
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.services.analysis_service import (
    AnalysisService,
    AnalysisServiceError,
)

from .auth import AuthContext, ScopeDependency

router = APIRouter(tags=["Analysis"])

require_data_scope = ScopeDependency("data")


class ScenarioUpsertRequest(BaseModel):
    name: str | None = None
    icon: str | None = None
    description: str | None = None
    instruction: str | None = None


class ScenarioCreateRequest(BaseModel):
    name: str
    icon: str | None = None
    description: str | None = None
    instruction: str


class ConversationRef(BaseModel):
    user_id: str
    cid: str


class AnalysisSessionRequest(BaseModel):
    platforms: list[str] | None = None
    keyword: str = ""
    message_types: list[str] | None = None
    created_after: int | None = None
    created_before: int | None = None
    conversations: list[ConversationRef] | None = None
    scenario_id: str = "intent"


class AnalysisExportRequest(AnalysisSessionRequest):
    format: Literal["csv", "jsonl"] = "csv"


def get_service(request: Request) -> AnalysisService:
    return request.app.state.services.analysis


async def _run(operation):
    try:
        return ok(await run_maybe_async(operation))
    except AnalysisServiceError as exc:
        raise ApiError(str(exc)) from exc


@router.get("/analysis/scenarios")
async def list_scenarios(
    _auth: AuthContext = Depends(require_data_scope),
    service: AnalysisService = Depends(get_service),
):
    return await _run(service.list_scenarios)


@router.post("/analysis/scenarios")
async def create_scenario(
    payload: ScenarioCreateRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: AnalysisService = Depends(get_service),
):
    return await _run(lambda: service.create_scenario(payload.model_dump()))


@router.put("/analysis/scenarios/{scenario_id}")
async def update_scenario(
    scenario_id: str,
    payload: ScenarioUpsertRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: AnalysisService = Depends(get_service),
):
    return await _run(
        lambda: service.update_scenario(scenario_id, payload.model_dump())
    )


@router.post("/analysis/scenarios/{scenario_id}/restore")
async def restore_scenario(
    scenario_id: str,
    _auth: AuthContext = Depends(require_data_scope),
    service: AnalysisService = Depends(get_service),
):
    return await _run(lambda: service.restore_scenario(scenario_id))


@router.delete("/analysis/scenarios/{scenario_id}")
async def delete_scenario(
    scenario_id: str,
    _auth: AuthContext = Depends(require_data_scope),
    service: AnalysisService = Depends(get_service),
):
    return await _run(lambda: service.delete_scenario(scenario_id))


@router.post("/analysis/sessions")
async def create_analysis_session(
    payload: AnalysisSessionRequest,
    auth: AuthContext = Depends(require_data_scope),
    service: AnalysisService = Depends(get_service),
):
    return await _run(
        lambda: service.create_analysis_session(
            auth.username,
            payload.model_dump(),
        )
    )


@router.post("/analysis/export")
async def export_analysis_conversations(
    payload: AnalysisExportRequest,
    _auth: AuthContext = Depends(require_data_scope),
    service: AnalysisService = Depends(get_service),
):
    try:
        filename, file_obj = await service.export_by_filter(payload.model_dump())
    except AnalysisServiceError as exc:
        raise ApiError(str(exc)) from exc
    except Exception as exc:
        logger.error(f"Analysis export failed: {exc}")
        raise
    file_obj.seek(0)

    def iter_file():
        while chunk := file_obj.read(8192):
            yield chunk

    return StreamingResponse(
        iter_file(),
        media_type="text/csv" if filename.endswith(".csv") else "application/jsonl",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

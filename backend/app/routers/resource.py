"""统一资源接口：查询、导出、登记和动作按模块 key 分派到领域服务。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, EntryPayload, PageResult
from app.services import service_for
from app.services.predict_coverage import predict_coverage_service
from app.store import store

router = APIRouter(prefix="/api", tags=["业务资源"])


def require_service(module: str):
    service = service_for(module)
    if service is None:
        raise HTTPException(status_code=404, detail=f"未知业务模块：{module}")
    return service


@router.get("/{module}", response_model=PageResult[dict])
def list_entries(
    module: str,
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    items, total = service.list_entries(
        filters=filters, keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# ── 预测覆盖视图：固定路径必须先于 /{module}/{entry_id} 注册 ──
@router.get("/predict-coverage/batches")
def list_coverage_batches() -> dict[str, Any]:
    """列出预测批次的覆盖状态，供覆盖视图左侧批次列表使用。"""
    return {"items": predict_coverage_service.list_batches()}


@router.get("/predict-coverage/batches/{batch_id}")
def get_coverage(batch_id: int) -> dict[str, Any]:
    """读取预测分片回执，返回已确认样本覆盖、缺失分片与高分占比。"""
    return predict_coverage_service.coverage(batch_id)


@router.post("/predict-coverage/batches/{batch_id}/receipts", response_model=ActionResult)
def submit_receipt(batch_id: int, payload: EntryPayload) -> ActionResult:
    """登记分片回执：迟到补交和重送都会追加新版本，旧版本保留用于回查。"""
    result = predict_coverage_service.submit_receipt(batch_id, payload.values)
    return ActionResult(ok=bool(result.get("ok")), message=str(result.get("message", "")),
                        entry=result)


@router.post("/predict-coverage/batches/{batch_id}/analyses", response_model=ActionResult)
def submit_coverage_analysis(batch_id: int, payload: EntryPayload) -> ActionResult:
    """挖掘结果管理读取覆盖视图的已确认范围，按实际入选行提交高分占比分析。"""
    result = service_for("mining_result").submit_coverage_analysis(batch_id, payload.values)
    return ActionResult(ok=bool(result.get("ok")), message=str(result.get("message", "")),
                        entry=result)


@router.get("/predict-coverage/analyses")
def list_coverage_analyses(batch_id: int | None = Query(default=None)) -> dict[str, Any]:
    """已完成洞察列表；覆盖分析按批次筛选，便于判断本轮是否已有可用比例。"""
    mining = service_for("mining_result")
    batch_ids = (
        [batch_id] if batch_id is not None
        else [int(row["id"]) for row in store.rows("predict_batch")]
    )
    items: list[dict[str, Any]] = []
    for bid in batch_ids:
        items.extend(mining.list_coverage_analyses(bid))
    return {"items": items}


@router.get("/predict-coverage/analyses/{result_id}")
def get_coverage_analysis(result_id: int) -> dict[str, Any]:
    """按原据回查一条覆盖分析：分子、分母、采用分区与原始回执。"""
    return predict_coverage_service.analysis_evidence(result_id)


@router.get("/{module}/export")
def export_entries(
    module: str,
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    service = require_service(module)
    filters = {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in service.LIST_FIELDS and value.strip()
    }
    items, _ = service.list_entries(
        filters=filters, keyword=keyword, status=status, page=1, size=1_000_000)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", *service.LIST_FIELDS, "status"])
    for item in items:
        values = [item.get("id"), *(item.get(field, "") for field in service.LIST_FIELDS),
                  item.get("status", "")]
        writer.writerow([
            "'" + str(value) if str(value or "").startswith(("=", "+", "-", "@")) else value
            for value in values
        ])
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{module}.csv"'},
    )


@router.get("/{module}/{entry_id}", response_model=dict)
def get_entry(module: str, entry_id: int) -> dict[str, Any]:
    service = require_service(module)
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{service.ENTITY} {entry_id} 不存在或已归档")
    return entry


@router.post("/{module}", response_model=ActionResult)
def create_entry(module: str, payload: EntryPayload) -> ActionResult:
    service = require_service(module)
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message=f"{service.ENTITY}已登记", entry=entry)


@router.post("/{module}/{entry_id}/actions", response_model=ActionResult)
def run_action(module: str, entry_id: int, payload: ActionPayload) -> ActionResult:
    service = require_service(module)
    entry, message = service.run_action(entry_id, payload.action.strip())
    return ActionResult(ok=entry is not None, message=message, entry=entry)

"""质检管理接口：维护质检单，覆盖开始检测、判定合格、判定不合格等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.quality import CONCLUSIONS, QualityService, parse_time_value

router = APIRouter(prefix="/api/quality", tags=["质检管理"])

service = QualityService()

LIST_FIELDS = ["质检单号", "关联批次", "检测项目", "检测值", "标准限值", "检测结论", "检测员", "检测时间"]
STATUSES = ["待检测", "检测中", "合格", "不合格"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按质检单号检索"),
    status: str | None = Query(default=None, description="待检测、检测中、合格、不合格"),
    item_name: str | None = Query(default=None, description="按检测项目模糊检索"),
    conclusion: str | None = Query(default=None, description="检测结论：合格、不合格、待复检"),
    inspector: str | None = Query(default=None, description="按检测员模糊检索"),
    begin_time: str | None = Query(default=None, description="检测时间起，YYYY-MM-DD[ HH:mm:ss]"),
    end_time: str | None = Query(default=None, description="检测时间止，YYYY-MM-DD[ HH:mm:ss]"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """多条件组合过滤质检单：所有非空条件同时生效，结果按检测时间倒序分页。

    条件不合法时返回 400 并说明原因，由前端回退到上一次查询结果。
    """
    if page < 1:
        raise HTTPException(status_code=400, detail="页码必须从 1 开始")
    if size < 1:
        raise HTTPException(status_code=400, detail="每页条数至少为 1")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"检测状态只能是：{'、'.join(STATUSES)}")
    if conclusion is not None and conclusion not in CONCLUSIONS:
        raise HTTPException(status_code=400, detail=f"检测结论只能是：{'、'.join(CONCLUSIONS)}")
    try:
        begin = parse_time_value(begin_time, field_name="检测开始时间")
        end = parse_time_value(end_time, field_name="检测结束时间")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if begin is not None and end is not None and begin > end:
        raise HTTPException(status_code=400, detail="检测开始时间不能晚于结束时间")
    items, total = service.list_entries(
        keyword=(keyword.strip() if keyword and keyword.strip() else None),
        status=status,
        item_name=(item_name.strip() if item_name and item_name.strip() else None),
        conclusion=conclusion,
        inspector=(inspector.strip() if inspector and inspector.strip() else None),
        begin_time=begin,
        end_time=end,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出质检管理清单：按检测时间倒序返回全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "quality", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条质检单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"质检单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条质检单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="质检单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条质检单执行开始检测、判定合格、判定不合格；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

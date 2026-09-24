"""质检管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "quality"
REQUIRED_FIELDS = ["质检单号", "关联批次", "检测项目"]
STATUS_ORDER = ["待检测", "检测中", "合格", "不合格"]
ACTION_RULES = {"开始检测": "检测中", "判定合格": "合格", "判定不合格": "不合格"}
NEGATIVE_ACTIONS = []

# 检测结论的取值固定，后端据此校验过滤条件
CONCLUSIONS = ["合格", "不合格", "待复检"]
TIME_FIELD = "检测时间"
TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d")


class QualityService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        item_name: str | None = None,
        conclusion: str | None = None,
        inspector: str | None = None,
        begin_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """多个条件同时生效（AND），按检测时间倒序后分页。

        条件值在进入这里前由路由层完成校验；时间区间在路由层解析为 datetime 后传入。
        """
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("质检单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if item_name:
            rows = [row for row in rows if item_name in str(row.get("检测项目", ""))]
        if conclusion:
            rows = [row for row in rows if str(row.get("检测结论", "")).strip() == conclusion]
        if inspector:
            rows = [row for row in rows if inspector in str(row.get("检测员", ""))]
        if begin_time is not None:
            rows = [
                row for row in rows
                if (stamp := _parse_time(row.get(TIME_FIELD))) is not None and stamp >= begin_time
            ]
        if end_time is not None:
            rows = [
                row for row in rows
                if (stamp := _parse_time(row.get(TIME_FIELD))) is not None and stamp <= end_time
            ]
        # 检测时间倒序；时间缺失或无法解析的记录排在最后，保持稳定次序
        rows.sort(
            key=lambda row: (_parse_time(row.get(TIME_FIELD)) is not None, _parse_time(row.get(TIME_FIELD)) or datetime.min),
            reverse=True,
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"质检单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于质检管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"质检单已{action}"


def parse_time_value(raw: str | None, *, field_name: str) -> datetime | None:
    """把查询参数里的时间文本解析成 datetime；空值视为不过滤，无法解析时抛出可读原因。"""
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"{field_name}格式无效：{text}，请使用 YYYY-MM-DD（可带时分秒）")


def _parse_time(value: Any) -> datetime | None:
    """解析记录上的检测时间；样例数据与登记数据可能缺时间，解析不了就排到最后。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None

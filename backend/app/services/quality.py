"""质检管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import re
from datetime import datetime, time
from typing import Any

from app.store import store

MODULE = "quality"
REQUIRED_FIELDS = ["质检单号", "关联批次", "检测项目"]
STATUS_ORDER = ["待检测", "检测中", "合格", "不合格"]
ACTION_RULES = {"开始检测": "检测中", "判定合格": "合格", "判定不合格": "不合格"}
NEGATIVE_ACTIONS = []

# 检测时间同时兼容「2026-09-01」与「2026-09-01 10:30:00」两种写法。
TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
# strptime 在部分平台会放行「2026-9-1」这类未补零写法，先用正则把格式卡死。
TIME_PATTERNS = (
    re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),
    re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"),
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
)

# 组合检索字段：接口参数 -> 列表列名（文本类统一做包含匹配）。
FILTER_FIELDS = {
    "keyword": "质检单号",
    "project": "检测项目",
    "inspector": "检测员",
}
# 检测结论是枚举型字段（合格/不合格），必须精确匹配，避免「合格」误命中「不合格」。
EXACT_FIELDS = {"conclusion": "检测结论"}


def parse_time(value: str) -> datetime:
    """把检测时间或区间端点解析成 datetime，无法识别时说明原因。"""
    text = value.strip()
    for pattern, fmt in zip(TIME_PATTERNS, TIME_FORMATS):
        if pattern.match(text):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                break  # 格式对得上但日期不存在，如 2026-13-40
    raise ValueError(f"检测时间「{value}」无效，请填写真实日期，格式为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")


def parse_row_time(row: dict[str, Any]) -> datetime | None:
    raw = row.get("检测时间")
    if raw in (None, ""):
        return None
    try:
        return parse_time(str(raw))
    except ValueError:
        return None


class QualityService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        project: str | None = None,
        conclusion: str | None = None,
        inspector: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """多条件组合检索：所有条件同时生效（AND），结果按检测时间倒序后分页。

        时间区间为闭区间，只填日期时起点按 00:00:00、终点按 23:59:59 处理；
        检测时间缺失或无法解析的记录，在指定时间条件时不参与命中。
        """
        start_dt = parse_time(start_time) if start_time else None
        end_dt = parse_time(end_time) if end_time else None
        if start_dt and end_dt and start_dt > end_dt:
            raise ValueError("检测时间区间无效：开始时间不能晚于结束时间")
        # 只填日期时，终点补到当天 23:59:59.999999，保证闭区间包含整天。
        if end_dt and len(end_time.strip()) == 10:  # type: ignore[union-attr]
            end_dt = datetime.combine(end_dt.date(), time.max)

        rows = store.rows(MODULE)
        for param, column in FILTER_FIELDS.items():
            needle = locals()[param]
            if needle:
                rows = [row for row in rows if needle in str(row.get(column) or "")]
        for param, column in EXACT_FIELDS.items():
            needle = locals()[param]
            if needle:
                rows = [row for row in rows if str(row.get(column) or "") == needle]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if start_dt or end_dt:
            timed: list[dict[str, Any]] = []
            for row in rows:
                row_dt = parse_row_time(row)
                if row_dt is None:
                    continue
                if start_dt and row_dt < start_dt:
                    continue
                if end_dt and row_dt > end_dt:
                    continue
                timed.append(row)
            rows = timed

        # 按检测时间倒序；时间缺失/异常的排到最后，同时间再按 id 倒序保持稳定。
        def sort_key(row: dict[str, Any]) -> tuple[bool, datetime, int]:
            row_dt = parse_row_time(row)
            return (row_dt is not None, row_dt or datetime.min, int(row.get("id", 0)))

        rows.sort(key=sort_key, reverse=True)

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

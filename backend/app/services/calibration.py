"""设备标定业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "calibration"
REQUIRED_FIELDS = ["标定编号", "标定对象", "标定机构"]
OPTIONAL_FIELDS = ["标定项目", "标定人员"]
STATUS_ORDER = ["待送检", "标定中", "标定合格", "标定不合格"]
ACTION_RULES = {"送检登记": "标定中", "确认合格": "标定合格", "判定不合格": "标定不合格"}
NEGATIVE_ACTIONS = ["判定不合格"]
TERMINAL_STATUSES = {"标定合格", "标定不合格"}
# 结论类动作只能打在「标定中」的记录上：判定不合格之后不能直接回到合格，
# 要复检必须先重新送检登记，避免合格/不合格来回切换。
CONCLUSION_ACTIONS = {"确认合格": "合格", "判定不合格": "不合格"}
VALIDITY_DAYS = 365


class CalibrationService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("标定编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
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
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS + OPTIONAL_FIELDS})
        entry["标定结论"] = None
        entry["有效期至"] = None
        entry["status"] = STATUS_ORDER[0]
        entry["标定状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"标定记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于设备标定可执行范围"
        current = str(entry.get("status") or "")
        if action in CONCLUSION_ACTIONS and current != "标定中":
            if current == "标定不合格" and action == "确认合格":
                return None, "记录已判定不合格，不能再回到合格，如需复检请先送检登记"
            return None, f"当前状态为「{current}」，请先送检登记再{action}"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        # 列表、详情、导出读的都是「标定状态」字段，必须和内部状态一起流转
        entry["标定状态"] = target
        entry["pending"] = target not in TERMINAL_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        # 标定结论跟着动作走；送检登记开启新一轮时清掉旧结论，不留残值
        entry["标定结论"] = CONCLUSION_ACTIONS.get(action)
        if action == "确认合格":
            entry["有效期至"] = (date.today() + timedelta(days=VALIDITY_DAYS)).isoformat()
        else:
            # 送检登记与判定不合格都不保留旧有效期，避免停留在上一次的结果
            entry["有效期至"] = None
        return entry, f"标定记录已{action}"

    def stats(self) -> list[dict[str, Any]]:
        """统计口径：同一标定对象只取最近一次记录，不合格单独计数。"""
        latest: dict[str, dict[str, Any]] = {}
        for row in store.rows(MODULE):
            key = str(row.get("标定对象") or row.get("id"))
            current = latest.get(key)
            if current is None or int(row.get("id", 0)) >= int(current.get("id", 0)):
                latest[key] = row
        rows = list(latest.values())

        def is_overdue(row: dict[str, Any]) -> bool:
            raw = str(row.get("有效期至") or "").strip()
            if not raw:
                return False
            try:
                return date.fromisoformat(raw) < date.today()
            except ValueError:
                return False

        return [
            {"label": "待送检设备", "value": sum(1 for row in rows if row.get("status") == "待送检")},
            {"label": "标定合格", "value": sum(1 for row in rows if row.get("status") == "标定合格")},
            {"label": "标定不合格", "value": sum(1 for row in rows if row.get("status") == "标定不合格")},
            {"label": "超期未标定", "value": sum(1 for row in rows if is_overdue(row))},
        ]

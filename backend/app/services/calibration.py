"""设备标定业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "calibration"
REQUIRED_FIELDS = ["标定编号", "标定对象", "标定机构"]
STATUS_ORDER = ["待送检", "标定中", "标定合格", "标定不合格"]
# 允许的状态流转：待送检 → 标定中 → 标定合格 / 标定不合格。
# 标定合格、标定不合格都是终态：判定不合格之后不能再回到合格，
# 同一台设备要重新标定时登记一条新的标定记录，统计按最近一次算。
ACTION_RULES = {
    "送检登记": {"from": {"待送检"}, "to": "标定中"},
    "确认合格": {"from": {"标定中"}, "to": "标定合格"},
    "判定不合格": {"from": {"标定中"}, "to": "标定不合格"},
}
# 会留下标定结论的动作；登记结论前必须已经填写标定机构。
CONCLUSION_ACTIONS = {"确认合格": "合格", "判定不合格": "不合格"}
NEGATIVE_ACTIONS = ["判定不合格"]
VALIDITY_DAYS = 365


def _default_valid_until() -> str:
    """确认合格时没给有效期，就按一年有效期顺延。"""
    return (date.today() + timedelta(days=VALIDITY_DAYS)).isoformat()


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
        for field in ["标定编号", "标定对象", "标定机构", "标定项目", "标定人员"]:
            value = values.get(field)
            if value is not None and str(value).strip():
                entry[field] = value
        # 新记录尚未送检：没有结论也没有有效期，标定状态跟随内部状态。
        entry["标定结论"] = ""
        entry["有效期至"] = ""
        entry["标定状态"] = STATUS_ORDER[0]
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"标定记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于设备标定可执行范围"
        rule = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current not in rule["from"]:
            allowed = "、".join(sorted(rule["from"]))
            return None, f"标定记录当前状态为「{current}」，仅「{allowed}」状态可执行{action}"
        conclusion = CONCLUSION_ACTIONS.get(action)
        if conclusion and not str(entry.get("标定机构") or "").strip():
            return None, "标定机构未填写，请先补充标定机构再登记标定结论"

        target = rule["to"]
        values = values or {}
        entry["status"] = target
        entry["标定状态"] = target
        entry["pending"] = target in {"待送检", "标定中"}
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if conclusion is None:
            # 重新送检：清掉上一次残留的标定结论与有效期。
            entry["标定结论"] = ""
            entry["有效期至"] = ""
        else:
            entry["标定结论"] = conclusion
            if action in NEGATIVE_ACTIONS:
                # 判定不合格：设备没有可用有效期，避免列表里残留上一次的有效期至。
                entry["有效期至"] = ""
            else:
                valid_until = str(values.get("有效期至") or "").strip()
                entry["有效期至"] = valid_until or _default_valid_until()
            operator = str(values.get("标定人员") or "").strip()
            if operator:
                entry["标定人员"] = operator
        return entry, f"标定记录已{action}"

    def stats(self) -> list[dict[str, Any]]:
        """标定统计：同一台设备（标定对象）有多条记录时只按最近一次（id 最大）计。"""
        latest: dict[str, dict[str, Any]] = {}
        for row in store.rows(MODULE):
            device = str(row.get("标定对象") or "").strip()
            key = device or f"__row_{row.get('id')}"
            if key not in latest or int(row.get("id", 0)) > int(latest[key].get("id", 0)):
                latest[key] = row
        rows = list(latest.values())
        today = date.today().isoformat()
        overdue = [
            row for row in rows
            if str(row.get("有效期至") or "").strip() and str(row.get("有效期至")) < today
        ]
        return [
            {"label": "待送检设备", "value": sum(1 for row in rows if row.get("status") == "待送检")},
            {"label": "标定合格", "value": sum(1 for row in rows if row.get("status") == "标定合格")},
            {"label": "标定不合格", "value": sum(1 for row in rows if row.get("status") == "标定不合格")},
            {"label": "超期未标定", "value": len(overdue)},
        ]

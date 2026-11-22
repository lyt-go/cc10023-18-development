"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

import copy
from typing import Any

from app.seed import SEED_ROWS
from app.seed_coverage import COVERAGE_SEED_ROWS


def _merged_seed() -> dict[str, list[dict[str, Any]]]:
    """模块样例与覆盖视图样例合并；同表按行追加，避免覆盖已有业务数据。"""
    merged: dict[str, list[dict[str, Any]]] = {
        name: [copy.deepcopy(row) for row in rows] for name, rows in SEED_ROWS.items()
    }
    for name, rows in COVERAGE_SEED_ROWS.items():
        merged.setdefault(name, []).extend(copy.deepcopy(row) for row in rows)
    return merged


class Store:
    def __init__(self) -> None:
        self._tables = _merged_seed()

    def module_names(self) -> list[str]:
        """对外可见的业务模块；下划线开头的是覆盖视图的内部凭据表。"""
        return sorted(name for name in self._tables if not name.startswith("_"))

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()

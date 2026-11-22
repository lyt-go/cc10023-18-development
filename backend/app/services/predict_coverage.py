"""预测覆盖视图领域服务。

覆盖视图不复制预测任务表，而是把「分片定义 + 数据回执」当作原始凭据：
只有拿到已确认回执的分片才提供样本，重复行键按第一次出现的人群只计一次。
成功回零行与缺回执是两种不同的分片状态，预计行数只作对照，不替代实收人数。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

# 高分判定阈值：回执里显式给了 high_score_flag 时以回执为准，否则按分数兜底。
HIGH_SCORE_THRESHOLD = 80

SHARD_CONFIRMED = "已确认"
SHARD_MISSING = "缺回执"
SHARD_PENDING = "待回执"

COVERAGE_COMPLETE = "完整"
COVERAGE_RESTRICTED = "受限"
COVERAGE_WAITING = "等待中"
COVERAGE_UNSPLIT = "未切片"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _row_is_high(row: dict[str, Any]) -> bool:
    flag = row.get("high_score_flag")
    if flag is not None:
        return bool(flag)
    try:
        return float(row.get("score")) >= HIGH_SCORE_THRESHOLD
    except (TypeError, ValueError):
        return False


class PredictCoverageService:
    """按预测批次汇总分片回执，输出已确认样本覆盖与受限结论。"""

    ENTITY = "预测覆盖视图"

    # ── 原始凭据读取 ──
    def _batch(self, batch_id: int) -> dict[str, Any] | None:
        return store.find("predict_batch", batch_id)

    def _shards(self, batch_id: int) -> list[dict[str, Any]]:
        rows = [
            row for row in store.rows("_predict_shards")
            if _as_int(row.get("batch_id")) == batch_id
        ]
        return sorted(rows, key=lambda row: (_as_int(row.get("sort_order")), row.get("shard_id", "")))

    def _receipts(self, batch_id: int) -> list[dict[str, Any]]:
        return [
            row for row in store.rows("_predict_receipts")
            if _as_int(row.get("batch_id")) == batch_id
        ]

    def _latest_receipt_map(self, batch_id: int) -> dict[str, dict[str, Any]]:
        """每个分片只采用版本号最大的一份回执；迟到补交、重送都以新版本生效。"""
        latest: dict[str, dict[str, Any]] = {}
        for receipt in self._receipts(batch_id):
            shard_id = str(receipt.get("shard_id", ""))
            current = latest.get(shard_id)
            if current is None or self._receipt_rank(receipt) > self._receipt_rank(current):
                latest[shard_id] = receipt
        return latest

    @staticmethod
    def _receipt_rank(receipt: dict[str, Any]) -> tuple[int, str, int]:
        return (
            _as_int(receipt.get("version")),
            str(receipt.get("received_at") or ""),
            _as_int(receipt.get("id")),
        )

    # ── 覆盖计算 ──
    def coverage(self, batch_id: int) -> dict[str, Any]:
        batch = self._batch(batch_id)
        if batch is None:
            return {"ok": False, "message": f"预测任务 {batch_id} 不存在"}

        shards = self._shards(batch_id)
        latest = self._latest_receipt_map(batch_id)

        # 按回执到达时间从早到晚合并，同一行键后到的数据覆盖先到的分数，但只保留一个样本。
        confirmed_receipts = [
            receipt for receipt in latest.values()
            if receipt.get("status") == SHARD_CONFIRMED
        ]
        confirmed_receipts.sort(key=self._receipt_rank)

        users: dict[str, dict[str, Any]] = {}
        source_map: dict[str, set[str]] = {}
        raw_rows = 0
        for receipt in confirmed_receipts:
            shard_id = str(receipt.get("shard_id", ""))
            for row in receipt.get("rows") or []:
                raw_rows += 1
                key = str(row.get("row_key") or "").strip()
                if not key:
                    continue
                users[key] = {
                    "row_key": key,
                    "score": row.get("score"),
                    "high_score": _row_is_high(row),
                }
                source_map.setdefault(key, set()).add(shard_id)

        shard_views: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for shard in shards:
            shard_id = str(shard.get("shard_id", ""))
            receipt = latest.get(shard_id)
            view = {
                "shard_id": shard_id,
                "expected_rows": _as_int(shard.get("预计行数")),
                "note": shard.get("说明", ""),
                "receipt_id": None,
                "receipt_version": None,
                "received_at": None,
                "row_count": None,
                "raw_rows": 0,
                "unique_rows": 0,
                "new_rows": 0,
                "duplicate_rows": 0,
                "status": SHARD_PENDING,
                "confirmed": False,
                "zero_row": False,
                "missing_reason": None,
                "delivery": None,
            }
            if receipt is None:
                shard_views.append(view)
                continue

            view.update({
                "receipt_id": receipt.get("receipt_id"),
                "receipt_version": _as_int(receipt.get("version")),
                "received_at": receipt.get("received_at"),
                "row_count": receipt.get("row_count"),
                "delivery": receipt.get("delivery"),
            })
            if receipt.get("status") == SHARD_CONFIRMED:
                rows = receipt.get("rows") or []
                keys = [str(row.get("row_key") or "").strip() for row in rows]
                keys = [key for key in keys if key]
                new_rows = [key for key in keys if key not in seen_keys]
                seen_keys.update(keys)
                view.update({
                    "status": SHARD_CONFIRMED,
                    "confirmed": True,
                    "zero_row": len(rows) == 0,
                    "raw_rows": len(rows),
                    "unique_rows": len(set(keys)),
                    "new_rows": len(set(new_rows)),
                    "duplicate_rows": len(keys) - len(set(new_rows)),
                    "missing_reason": None,
                })
            else:
                view["status"] = SHARD_MISSING
                view["missing_reason"] = str(receipt.get("status") or "回执未确认")
            shard_views.append(view)

        unique_rows = len(users)
        high_rows = sum(1 for user in users.values() if user["high_score"])
        missing_shards = [view["shard_id"] for view in shard_views if view["status"] == SHARD_MISSING]
        pending_shards = [view["shard_id"] for view in shard_views if view["status"] == SHARD_PENDING]
        confirmed_shards = [view["shard_id"] for view in shard_views if view["confirmed"]]
        expected_rows = sum(view["expected_rows"] for view in shard_views)

        if not shard_views:
            state = COVERAGE_UNSPLIT
        elif missing_shards or pending_shards:
            state = COVERAGE_RESTRICTED if confirmed_shards else COVERAGE_WAITING
        else:
            state = COVERAGE_COMPLETE

        user_rows = []
        for key in sorted(users):
            user_rows.append({**users[key], "source_shards": sorted(source_map.get(key, set()))})

        denominator = unique_rows
        return {
            "ok": True,
            "batch_id": batch_id,
            "batch_code": batch.get("任务编号"),
            "model_id": batch.get("模型编号"),
            "data_slice": batch.get("数据切片"),
            "batch_status": batch.get("预测状态") or batch.get("status"),
            "expected_rows": expected_rows,
            "planned_rows": _as_int(batch.get("预计行数")) or expected_rows,
            "shard_count": len(shard_views),
            "confirmed_shard_count": len(confirmed_shards),
            "missing_shard_count": len(missing_shards),
            "pending_shard_count": len(pending_shards),
            "shards": shard_views,
            "confirmed_shards": confirmed_shards,
            "missing_shards": missing_shards,
            "pending_shards": pending_shards,
            "covered_rows": unique_rows,
            "raw_rows": raw_rows,
            "duplicate_rows": max(raw_rows - unique_rows, 0),
            "high_score_rows": high_rows,
            "numerator": high_rows,
            "denominator": denominator,
            "high_score_ratio": (
                None if denominator == 0 else round(high_rows / denominator, 6)
            ),
            "ratio_fraction": f"{high_rows}/{denominator}",
            "coverage_state": state,
            "complete": state == COVERAGE_COMPLETE,
            "users": user_rows,
            "metric_note": "分母为已确认回执去重后的实际入选行，预计行数仅作对照",
        }

    # ── 回执接收 ──
    def submit_receipt(self, batch_id: int, values: dict[str, Any]) -> dict[str, Any]:
        batch = self._batch(batch_id)
        if batch is None:
            return {"ok": False, "message": f"预测任务 {batch_id} 不存在"}
        shard_id = str(values.get("shard_id") or "").strip()
        shard = next(
            (item for item in self._shards(batch_id)
             if str(item.get("shard_id", "")) == shard_id),
            None,
        )
        if shard is None:
            return {"ok": False, "message": f"分片 {shard_id or '（空）'} 不属于预测任务 {batch_id}"}

        status = str(values.get("status") or SHARD_CONFIRMED)
        if status not in (SHARD_CONFIRMED, SHARD_MISSING):
            return {"ok": False, "message": f"回执状态 {status} 不合法"}

        raw_rows = values.get("rows") or []
        if not isinstance(raw_rows, list):
            return {"ok": False, "message": "rows 必须是行对象列表"}
        if status != SHARD_CONFIRMED:
            raw_rows = []
        rows: list[dict[str, Any]] = []
        for item in raw_rows:
            if not isinstance(item, dict):
                return {"ok": False, "message": "回执行必须是对象列表"}
            row_key = str(item.get("row_key") or "").strip()
            if not row_key:
                return {"ok": False, "message": "回执行缺少 row_key"}
            score = item.get("score")
            if score is not None:
                try:
                    score = float(score)
                except (TypeError, ValueError):
                    return {"ok": False, "message": f"行 {row_key} 的 score 不是数值"}
            rows.append({
                "row_key": row_key,
                "score": score,
                "high_score_flag": item.get("high_score_flag"),
            })

        existing = [
            receipt for receipt in self._receipts(batch_id)
            if str(receipt.get("shard_id", "")) == shard_id
        ]
        version = max((_as_int(item.get("version")) for item in existing), default=0) + 1
        if not existing:
            delivery = "initial"
        elif any(item.get("status") == SHARD_CONFIRMED for item in existing):
            delivery = "resend"
        else:
            delivery = "late"

        receipt = {
            "id": max((_as_int(row.get("id")) for row in store.rows("_predict_receipts")), default=0) + 1,
            "receipt_id": f"RCPT-{batch_id}-{shard_id}-v{version}",
            "batch_id": batch_id,
            "shard_id": shard_id,
            "version": version,
            "status": status,
            "delivery": delivery,
            "rows": rows,
            "row_count": len(rows) if status == SHARD_CONFIRMED else None,
            "received_at": _now() if status == SHARD_CONFIRMED else values.get("received_at"),
            "note": str(values.get("note") or ""),
        }
        store.rows("_predict_receipts").append(receipt)
        return {
            "ok": True,
            "message": f"分片 {shard_id} 回执已登记为 v{version}（{status}）",
            "receipt": receipt,
            "coverage": self.coverage(batch_id),
        }

    # ── 洞察记录回查 ──
    def analysis_evidence(self, result_id: int) -> dict[str, Any]:
        """按洞察记录回查当时采用的覆盖分区与回执原始凭据。"""
        record = store.find("mining_result", result_id)
        if record is None or record.get("算法类型") != "coverage_ratio":
            return {"ok": False, "message": f"覆盖分析洞察 {result_id} 不存在"}
        receipt_ids = set(record.get("凭据回执") or [])
        receipts = []
        for receipt in store.rows("_predict_receipts"):
            if receipt.get("receipt_id") in receipt_ids:
                receipts.append({
                    "receipt_id": receipt.get("receipt_id"),
                    "shard_id": receipt.get("shard_id"),
                    "version": receipt.get("version"),
                    "status": receipt.get("status"),
                    "delivery": receipt.get("delivery"),
                    "row_count": receipt.get("row_count"),
                    "received_at": receipt.get("received_at"),
                    "rows": receipt.get("rows"),
                })
        return {
            "ok": True,
            "insight": record,
            "score": {
                "numerator": record.get("分子"),
                "denominator": record.get("分母"),
                "ratio": record.get("高分占比"),
                "coverage_state": record.get("覆盖状态"),
            },
            "partitions": record.get("采用分区") or [],
            "missing_partitions": record.get("缺失分区") or [],
            "receipts": receipts,
        }

    # ── 列表与概览 ──
    def list_batches(self) -> list[dict[str, Any]]:
        batches = []
        for batch in store.rows("predict_batch"):
            snapshot = self.coverage(_as_int(batch.get("id")))
            if not snapshot.get("ok"):
                continue
            batches.append({
                "batch_id": snapshot["batch_id"],
                "batch_code": snapshot["batch_code"],
                "model_id": snapshot["model_id"],
                "data_slice": snapshot["data_slice"],
                "coverage_state": snapshot["coverage_state"],
                "complete": snapshot["complete"],
                "covered_rows": snapshot["covered_rows"],
                "planned_rows": snapshot["planned_rows"],
                "ratio_fraction": snapshot["ratio_fraction"],
                "confirmed_shard_count": snapshot["confirmed_shard_count"],
                "shard_count": snapshot["shard_count"],
                "missing_shards": snapshot["missing_shards"],
                "pending_shards": snapshot["pending_shards"],
            })
        return batches

predict_coverage_service = PredictCoverageService()

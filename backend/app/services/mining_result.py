"""挖掘结果管理领域服务：分析结果、洞察发现与关键发现的管理。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class MiningResultService(BaseModuleService):
    MODULE = "mining_result"
    ENTITY = "挖掘结果"
    OPERATION_TERM = "存储"
    LIST_FIELDS = ["结果编号", "分析主题", "算法类型", "洞察摘要", "关键分群", "置信度", "结果文件", "结果版本"]
    REQUIRED_FIELDS = ["结果编号", "分析主题", "算法类型"]
    STATUS_ORDER = ["草稿", "审核中", "已采纳", "已搁置"]
    ACTION_RULES = {"提交审核": "审核中", "确认采纳": "已采纳", "标记搁置": "已搁置"}
    NEGATIVE_ACTIONS = []

    # ── 覆盖链: 预测覆盖视图 → 挖掘结果 ──
    def submit_coverage_analysis(
        self, batch_id: int, values: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """读取预测覆盖视图的已确认范围，按实际入选行计算高分用户占比。

        分母只算已确认回执去重后的实际行数，不用预计行数凑数；
        缺片时结论标记为受限，不能把不完整样本说成完整结论。
        """
        from app.services.predict_coverage import (
            COVERAGE_COMPLETE,
            predict_coverage_service,
        )

        values = values or {}
        snapshot = predict_coverage_service.coverage(batch_id)
        if not snapshot.get("ok"):
            return snapshot
        if snapshot["denominator"] == 0:
            if snapshot["shard_count"] == 0:
                return {
                    "ok": False,
                    "waiting": True,
                    "message": "该预测批次尚未切片，没有可分片回执，无法计算占比",
                    "coverage": snapshot,
                }
            if snapshot["coverage_state"] == COVERAGE_COMPLETE:
                return {
                    "ok": False,
                    "waiting": False,
                    "message": "全部分片已确认但实收 0 行，样本分母为 0，无法计算占比",
                    "coverage": snapshot,
                }
            return {
                "ok": True,
                "waiting": True,
                "message": "尚无已确认回执，样本分母为 0，本轮分析仍在等待",
                "coverage": snapshot,
            }

        sequence = len(self.list_coverage_analyses(batch_id)) + 1
        ratio = snapshot["high_score_ratio"]
        restricted = snapshot["coverage_state"] != COVERAGE_COMPLETE
        if restricted:
            missing = "、".join(snapshot["missing_shards"] + snapshot["pending_shards"]) or "未知分片"
            conclusion = f"受限：分片 {missing} 尚无已确认回执，结论只覆盖已确认样本"
        else:
            conclusion = "完整：全部分片已确认，结论覆盖整个预测批次"
        summary = f"高分用户占比 {snapshot['ratio_fraction']}（{ratio:.4f}），{conclusion}"

        rows = store.rows(self.MODULE)
        next_id = max((_as_int(row.get("id")) for row in rows), default=0) + 1
        record = {
            "id": next_id,
            "status": "已采纳",
            "pending": False,
            "abnormal": False,
            "结果编号": f"RES-COV-{batch_id:04d}-{sequence:04d}",
            "分析主题": f"预测批次 {snapshot['batch_code']} 高分用户占比分析",
            "算法类型": "coverage_ratio",
            "洞察摘要": summary,
            "关键分群": "高分用户,其他用户",
            "置信度": f"{ratio:.4f}",
            "结果文件": f"coverage/{snapshot['batch_code']}/analysis_{sequence:04d}.json",
            "结果版本": f"v{sequence}.0.0",
            # 洞察记录必须能原据回查：分子、分母、批次、实际采用的分区、凭据回执都在这里。
            "分子": snapshot["numerator"],
            "分母": snapshot["denominator"],
            "高分占比": snapshot["ratio_fraction"],
            "占比小数": ratio,
            "预测批次": snapshot["batch_code"],
            "预测批次ID": batch_id,
            "采用分区": list(snapshot["confirmed_shards"]),
            "缺失分区": list(snapshot["missing_shards"]),
            "等待分区": list(snapshot["pending_shards"]),
            "覆盖状态": snapshot["coverage_state"],
            "结论状态": "受限" if restricted else "完整",
            "实际入选行数": snapshot["covered_rows"],
            "去重重复行数": snapshot["duplicate_rows"],
            "预计行数": snapshot["planned_rows"],
            "凭据回执": [
                shard["receipt_id"] for shard in snapshot["shards"] if shard["confirmed"]
            ],
            "统计口径": "已确认回执内行键去重，每个行键只计一次；预计行数不替代实收人数",
            "提交人": str(values.get("submitted_by") or "data_analyst"),
            "提交时间": _now(),
        }
        rows.append(record)
        return {
            "ok": True,
            "message": f"高分占比分析已记录：{snapshot['ratio_fraction']}（{record['结论状态']}）",
            "insight": record,
            "coverage": snapshot,
        }

    def list_coverage_analyses(self, batch_id: int) -> list[dict[str, Any]]:
        return [
            row for row in store.rows(self.MODULE)
            if row.get("算法类型") == "coverage_ratio"
            and _as_int(row.get("预测批次ID")) == batch_id
        ]

    # ── 链路4: 预测 → 挖掘结果 ──
    def export_insights_to_labels(self, result_id: int) -> dict[str, Any]:
        """将挖掘结果的关键发现导出到业务场景标注模块，形成可复用的场景规则。"""
        result = store.find(self.MODULE, result_id)
        if result is None:
            return {"ok": False}
        label_rows = store.rows("scenario_label")
        next_id = max((int(r.get("id", 0)) for r in label_rows), default=0) + 1
        result["status"] = "已采纳"
        result["pending"] = False
        label_rows.append({
            "id": next_id,
            "status": "草稿",
            "pending": True,
            "abnormal": False,
            "标注编号": f"LABEL-{next_id:04d}",
            "场景名称": f"挖掘场景_{result.get('分析主题', 'unknown')}",
            "关联特征": result.get("关键分群", ""),
            "业务规则": result.get("洞察摘要", ""),
            "标注时间": "2026-11-18",
            "标注人": "system_auto",
            "标注状态": "草稿",
            "场景版本": "v1.0.0",
        })
        return {"ok": True, "result_id": result_id, "label_id": next_id}

    def aggregate_cluster_insights(self, result_id: int) -> dict[str, Any]:
        """聚合挖掘结果中关键分群的洞察数据并关联到聚类分析配置。"""
        result = store.find(self.MODULE, result_id)
        if result is None:
            return {"ok": False}
        cluster_rows = store.rows("cluster_config")
        related_clusters = [
            r.get("id") for r in cluster_rows
            if result.get("关键分群", "") and any(g.strip() in str(r.get("特征集", ""))
            for g in result.get("关键分群", "").split(","))
        ]
        return {
            "ok": True,
            "result_id": result_id,
            "clusters": result.get("关键分群", "").split(","),
            "related_cluster_configs": related_clusters,
        }

    def convert_insight_to_feature_source(self, result_id: int) -> dict[str, Any]:
        """将采纳的挖掘洞察转换为新的特征数据源，丰富下游模型的特征输入。"""
        result = store.find(self.MODULE, result_id)
        if result is None:
            return {"ok": False}
        source_rows = store.rows("feature_source")
        next_id = max((int(r.get("id", 0)) for r in source_rows), default=0) + 1
        source_rows.append({
            "id": next_id,
            "status": "草稿",
            "pending": True,
            "abnormal": False,
            "源编号": f"SRC-R{result_id:04d}",
            "源名称": f"洞察衍生特征_{result.get('分析主题', '')}",
            "数据表名": f"insight_derived_{result_id}",
            "连接配置": "hive_metastore",
            "字段清单": "insight_score,cluster_label,confidence",
            "采样比例": "0.5",
            "缓存策略": "memory_1h",
            "源版本": "v1.0.0",
        })
        return {"ok": True, "source_id": next_id, "result_id": result_id}

    def deduplicate_mining_results(self, result_ids: list[int]) -> dict[str, Any]:
        """对挖掘结果集进行去重处理，识别相似洞察并合并重复发现。"""
        topics = {}
        duplicates = []
        for rid in result_ids:
            r = store.find(self.MODULE, rid)
            if r is None:
                continue
            topic = r.get("分析主题", "")
            if topic in topics:
                duplicates.append({"id": rid, "similar_to": topics[topic]})
                r["status"] = "已搁置"
            else:
                topics[topic] = rid
        return {"ok": True, "unique_count": len(topics), "duplicate_count": len(duplicates),
                "duplicates": duplicates}
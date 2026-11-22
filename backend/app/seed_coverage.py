"""预测覆盖视图样例数据。

覆盖视图不新增业务实体表，只围绕一个真实的预测批次准备分片定义与回执：
分片 A、B 已确认且带有重复行键，分片 D 成功返回 0 行，分片 C 超时无回执。
这样打开页面就能看到“已确认 2 人、缺片 C、零行成功 D”的初始现场。
"""
from __future__ import annotations

from typing import Any

COVERAGE_BATCH_ID = 4

COVERAGE_SEED_ROWS: dict[str, list[dict[str, Any]]] = {
    "predict_batch": [
        {
            "id": COVERAGE_BATCH_ID,
            "status": "运行中",
            "pending": True,
            "abnormal": False,
            "任务编号": "PRED-COV-0001",
            "模型编号": "MODE-0003",
            "数据切片": "高价值用户近30天行为切片",
            "输出格式": "csv",
            "分片策略": "按用户键哈希分4片",
            "并行度": "4",
            "预测状态": "运行中",
            "结果校验": "待校验",
            "预计行数": 5,
        }
    ],
    "_predict_shards": [
        {"id": 1, "batch_id": COVERAGE_BATCH_ID, "shard_id": "A", "预计行数": 1,
         "sort_order": 1, "说明": "首片"},
        {"id": 2, "batch_id": COVERAGE_BATCH_ID, "shard_id": "B", "预计行数": 2,
         "sort_order": 2, "说明": "第二片"},
        {"id": 3, "batch_id": COVERAGE_BATCH_ID, "shard_id": "C", "预计行数": 1,
         "sort_order": 3, "说明": "第三片"},
        {"id": 4, "batch_id": COVERAGE_BATCH_ID, "shard_id": "D", "预计行数": 1,
         "sort_order": 4, "说明": "第四片"},
    ],
    # 回执是不可变凭据：迟到补交、重送都会追加新版本，旧版本保留用于回查。
    "_predict_receipts": [
        {
            "id": 1,
            "receipt_id": "RCPT-4-A-v1",
            "batch_id": COVERAGE_BATCH_ID,
            "shard_id": "A",
            "version": 1,
            "status": "已确认",
            "delivery": "initial",
            "rows": [
                {"row_key": "user_1001", "score": 92, "high_score_flag": True},
            ],
            "row_count": 1,
            "received_at": "2026-11-22T09:10:00+08:00",
            "note": "首片回执，1 行高分用户",
        },
        {
            "id": 2,
            "receipt_id": "RCPT-4-B-v1",
            "batch_id": COVERAGE_BATCH_ID,
            "shard_id": "B",
            "version": 1,
            "status": "已确认",
            "delivery": "initial",
            "rows": [
                {"row_key": "user_1001", "score": 92, "high_score_flag": True},
                {"row_key": "user_1002", "score": 35, "high_score_flag": False},
            ],
            "row_count": 2,
            "received_at": "2026-11-22T09:12:00+08:00",
            "note": "第二片回执，2 行；user_1001 与首片重复，只计一次",
        },
        {
            "id": 3,
            "receipt_id": "RCPT-4-C-v1",
            "batch_id": COVERAGE_BATCH_ID,
            "shard_id": "C",
            "version": 1,
            "status": "超时",
            "delivery": "timeout",
            "rows": [],
            "row_count": None,
            "received_at": None,
            "note": "第三片执行超时，回执未到（不是 0 行）",
        },
        {
            "id": 4,
            "receipt_id": "RCPT-4-D-v1",
            "batch_id": COVERAGE_BATCH_ID,
            "shard_id": "D",
            "version": 1,
            "status": "已确认",
            "delivery": "initial",
            "rows": [],
            "row_count": 0,
            "received_at": "2026-11-22T09:15:00+08:00",
            "note": "第四片执行成功，返回 0 行",
        },
    ],
}

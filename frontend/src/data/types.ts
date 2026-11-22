/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

/** 预测覆盖视图：分片回执状态与按行去重后的已确认样本。 */
export type CoverageShard = {
  shard_id: string
  expected_rows: number
  note: string
  receipt_id: string | null
  receipt_version: number | null
  received_at: string | null
  row_count: number | null
  raw_rows: number
  unique_rows: number
  new_rows: number
  duplicate_rows: number
  status: string
  confirmed: boolean
  zero_row: boolean
  missing_reason: string | null
  delivery: string | null
}

export type CoverageUser = {
  row_key: string
  score: number | null
  high_score: boolean
  source_shards: string[]
}

export type CoverageSnapshot = {
  ok: boolean
  message?: string
  batch_id: number
  batch_code: string
  model_id: string
  data_slice: string
  batch_status: string
  expected_rows: number
  planned_rows: number
  shard_count: number
  confirmed_shard_count: number
  missing_shard_count: number
  pending_shard_count: number
  shards: CoverageShard[]
  confirmed_shards: string[]
  missing_shards: string[]
  pending_shards: string[]
  covered_rows: number
  raw_rows: number
  duplicate_rows: number
  high_score_rows: number
  numerator: number
  denominator: number
  high_score_ratio: number | null
  ratio_fraction: string
  coverage_state: string
  complete: boolean
  users: CoverageUser[]
  metric_note: string
}

export type CoverageBatchSummary = {
  batch_id: number
  batch_code: string
  model_id: string
  data_slice: string
  coverage_state: string
  complete: boolean
  covered_rows: number
  planned_rows: number
  ratio_fraction: string
  confirmed_shard_count: number
  shard_count: number
  missing_shards: string[]
  pending_shards: string[]
}

export type CoverageInsight = {
  id: number
  结果编号: string
  分析主题: string
  洞察摘要: string
  分子: number
  分母: number
  高分占比: string
  预测批次: string
  采用分区: string[]
  缺失分区: string[]
  等待分区: string[]
  覆盖状态: string
  结论状态: string
  预计行数: number
  去重重复行数: number
  提交时间: string
  [field: string]: unknown
}

export type CoverageAnalysisResult = {
  ok: boolean
  waiting?: boolean
  message: string
  entry?: {
    insight?: CoverageInsight
    coverage?: CoverageSnapshot
    waiting?: boolean
  }
}

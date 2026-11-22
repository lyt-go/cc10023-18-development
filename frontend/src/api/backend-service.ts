import { request, fetchJson } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  CoverageAnalysisResult,
  CoverageBatchSummary,
  CoverageInsight,
  CoverageSnapshot,
  EntryRow,
  OverviewResult,
  PageResult,
} from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

// ── 预测覆盖视图 ──
export async function listCoverageBatches(): Promise<CoverageBatchSummary[]> {
  const payload = await fetchJson<{ items: CoverageBatchSummary[] }>('/api/predict-coverage/batches')
  return payload.items
}

export async function loadCoverage(batchId: number): Promise<CoverageSnapshot> {
  return await fetchJson<CoverageSnapshot>(`/api/predict-coverage/batches/${batchId}`)
}

export async function submitReceipt(
  batchId: number,
  values: Record<string, unknown>,
): Promise<CoverageAnalysisResult> {
  const response = await request(`/api/predict-coverage/batches/${batchId}/receipts`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function submitCoverageAnalysis(
  batchId: number,
  values: Record<string, unknown> = {},
): Promise<CoverageAnalysisResult> {
  const response = await request(`/api/predict-coverage/batches/${batchId}/analyses`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function listCoverageAnalyses(batchId: number): Promise<CoverageInsight[]> {
  const payload = await fetchJson<{ items: CoverageInsight[] }>(
    `/api/predict-coverage/analyses?batch_id=${batchId}`,
  )
  return payload.items
}

export type CoverageEvidence = {
  ok: boolean
  insight: CoverageInsight
  score: { numerator: number; denominator: number; ratio: string; coverage_state: string }
  partitions: string[]
  missing_partitions: string[]
  receipts: {
    receipt_id: string
    shard_id: string
    version: number
    status: string
    delivery: string
    row_count: number | null
    received_at: string | null
  }[]
}

export async function loadCoverageEvidence(resultId: number): Promise<CoverageEvidence> {
  return await fetchJson<CoverageEvidence>(`/api/predict-coverage/analyses/${resultId}`)
}

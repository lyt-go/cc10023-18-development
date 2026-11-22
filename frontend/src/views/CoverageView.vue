<template>
  <section class="page coverage-page" data-testid="coverage-view">
    <header class="page-head">
      <div>
        <h2>预测覆盖情况</h2>
        <p class="page-desc">
          读取预测分片数据回执，按已确认回执的行键去重，回答预测实际覆盖了多少人。
          预计行数只作对照，不替代实收人数。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="coverage-refresh" type="button" @click="reload">
          重新打开覆盖视图
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card" data-testid="coverage-covered">
        <span class="stat-label">已确认覆盖人数</span>
        <strong class="stat-value">{{ snapshot?.covered_rows ?? 0 }}</strong>
      </article>
      <article class="stat-card" data-testid="coverage-state-card">
        <span class="stat-label">覆盖状态</span>
        <strong class="stat-value" :data-state="snapshot?.coverage_state">{{ snapshot?.coverage_state ?? '—' }}</strong>
      </article>
      <article class="stat-card" data-testid="coverage-ratio">
        <span class="stat-label">高分占比（已确认口径）</span>
        <strong class="stat-value">{{ snapshot?.ratio_fraction ?? '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">预计行数（仅对照）</span>
        <strong class="stat-value">{{ snapshot?.planned_rows ?? 0 }}</strong>
      </article>
    </div>

    <div class="coverage-layout">
      <aside class="coverage-batches">
        <h3>预测批次</h3>
        <button
          v-for="batch in batches"
          :key="batch.batch_id"
          type="button"
          class="coverage-batch"
          :class="{ active: batch.batch_id === activeBatchId }"
          :data-testid="`coverage-batch-${batch.batch_id}`"
          @click="selectBatch(batch.batch_id)"
        >
          <span class="coverage-batch-code">{{ batch.batch_code }}</span>
          <span class="coverage-batch-state" :data-state="batch.coverage_state">{{ batch.coverage_state }}</span>
          <small>{{ batch.covered_rows }}/{{ batch.planned_rows }} 行 · 分片 {{ batch.confirmed_shard_count }}/{{ batch.shard_count }}</small>
        </button>
        <p v-if="!batches.length" class="empty-state">暂无预测批次</p>
      </aside>

      <div class="coverage-main">
        <p v-if="errorMessage" class="error-text" data-testid="coverage-error">{{ errorMessage }}</p>

        <div v-if="snapshot" class="coverage-banner" :data-state="snapshot.coverage_state" data-testid="coverage-banner">
          <strong>{{ snapshot.batch_code }}</strong>
          <span>{{ snapshot.data_slice }} · 模型 {{ snapshot.model_id }}</span>
          <span>{{ stateText }}</span>
          <span>实收 {{ snapshot.covered_rows }} 人 / 预计 {{ snapshot.planned_rows }} 行</span>
          <span v-if="snapshot.duplicate_rows">重复行键 {{ snapshot.duplicate_rows }} 条，已按一人计一次</span>
        </div>

        <table class="data-table" data-testid="coverage-shard-table">
          <thead>
            <tr>
              <th>分片</th>
              <th>回执状态</th>
              <th>回执版本</th>
              <th>预计行数</th>
              <th>实收行数</th>
              <th>新增人群</th>
              <th>重复行键</th>
              <th>到达时间</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="shard in snapshot?.shards ?? []"
              :key="shard.shard_id"
              :data-testid="`coverage-shard-${shard.shard_id}`"
              :data-shard-status="shard.status"
            >
              <td>{{ shard.shard_id }}（{{ shard.note || '分片' }}）</td>
              <td>
                <span class="shard-status" :data-state="shard.status">
                  {{ shard.status }}<template v-if="shard.zero_row">（0 行）</template>
                </span>
                <small v-if="shard.missing_reason" class="shard-reason">{{ shard.missing_reason }}</small>
              </td>
              <td>{{ shard.receipt_version ? `v${shard.receipt_version}` : '—' }}</td>
              <td>{{ shard.expected_rows }}</td>
              <td data-testid="shard-row-count">
                {{ shard.row_count === null ? '未到（≠0）' : shard.row_count }}
              </td>
              <td>{{ shard.new_rows }}</td>
              <td>{{ shard.duplicate_rows }}</td>
              <td>{{ shard.received_at ?? '—' }}</td>
              <td>{{ shard.delivery === 'late' ? '迟到补交' : shard.delivery === 'resend' ? '重送回执' : shard.note }}</td>
            </tr>
          </tbody>
        </table>

        <div class="coverage-users">
          <h3>已确认覆盖人群（按行键去重）</h3>
          <p v-if="!snapshot?.users.length" class="coverage-hint" data-testid="coverage-users-empty">
            尚无已确认用户行
          </p>
          <table v-else class="data-table" data-testid="coverage-user-table">
            <thead>
              <tr><th>行键</th><th>分数</th><th>是否高分</th><th>出现分片</th></tr>
            </thead>
            <tbody>
              <tr
                v-for="user in snapshot.users"
                :key="user.row_key"
                :data-testid="`coverage-user-${user.row_key}`"
                :data-high-score="user.high_score"
              >
                <td>{{ user.row_key }}</td>
                <td>{{ user.score ?? '—' }}</td>
                <td>{{ user.high_score ? '高分' : '其他' }}</td>
                <td>{{ user.source_shards.join('、') }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="coverage-analysis">
          <div>
            <h3>按已确认范围提交高分占比分析</h3>
            <p class="coverage-hint">
              分子 {{ snapshot?.numerator ?? 0 }}、分母 {{ snapshot?.denominator ?? 0 }} 来自上方已确认回执；
              缺片时洞察记录会标注「受限」，不会把预计数当成实收人数。
            </p>
          </div>
          <button
            class="btn primary"
            data-testid="submit-coverage-analysis"
            type="button"
            :disabled="submitting"
            @click="submitAnalysis"
          >
            {{ submitting ? '提交中…' : '提交分析' }}
          </button>
        </div>

        <form class="coverage-receipt" data-testid="receipt-form" @submit.prevent="submitReceiptForm">
          <h3>登记分片回执</h3>
          <p class="coverage-hint">
            迟到补交或重送都会追加新版本，旧版本保留用于原据回查；同一行键重复出现只计一人。
          </p>
          <div class="receipt-row">
            <label>
              <span>分片</span>
              <select v-model="receiptForm.shardId" data-testid="receipt-shard" required>
                <option v-for="shard in snapshot?.shards ?? []" :key="shard.shard_id" :value="shard.shard_id">
                  {{ shard.shard_id }}（{{ shard.status }}）
                </option>
              </select>
            </label>
            <label>
              <span>回执结果</span>
              <select v-model="receiptForm.status" data-testid="receipt-status">
                <option value="已确认">已确认（含 0 行）</option>
                <option value="缺回执">仍缺回执</option>
              </select>
            </label>
            <label class="receipt-note">
              <span>备注</span>
              <input v-model="receiptForm.note" data-testid="receipt-note" placeholder="如：迟到补交 / 重送" />
            </label>
          </div>
          <div v-if="receiptForm.status === '已确认'" class="receipt-rows">
            <div v-for="(row, index) in receiptForm.rows" :key="index" class="receipt-row">
              <label>
                <span>行键</span>
                <input v-model="row.rowKey" :data-testid="`receipt-row-key-${index}`" placeholder="user_1003" required />
              </label>
              <label>
                <span>分数</span>
                <input v-model="row.score" :data-testid="`receipt-row-score-${index}`" type="number" step="any" required />
              </label>
              <button class="link" type="button" @click="removeReceiptRow(index)">删除</button>
            </div>
            <button class="btn ghost" data-testid="receipt-add-row" type="button" @click="addReceiptRow">
              + 新增一行
            </button>
          </div>
          <div class="page-actions">
            <button class="btn primary" data-testid="submit-receipt" type="submit" :disabled="submittingReceipt">
              {{ submittingReceipt ? '登记中…' : '登记回执' }}
            </button>
          </div>
          <p v-if="receiptNotice" class="coverage-hint" data-testid="receipt-notice">{{ receiptNotice }}</p>
        </form>

        <div v-if="analysisNotice" class="coverage-notice" :class="{ waiting: analysisNotice.waiting }" data-testid="analysis-notice">
          {{ analysisNotice.message }}
        </div>

        <h3>已完成覆盖洞察</h3>
        <table class="data-table" data-testid="coverage-analysis-table">
          <thead>
            <tr>
              <th>结果编号</th>
              <th>分子/分母</th>
              <th>高分占比</th>
              <th>预测批次</th>
              <th>采用分区</th>
              <th>缺失分区</th>
              <th>覆盖状态</th>
              <th>结论</th>
              <th>预计行数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="insight in analyses"
              :key="insight.id"
              :data-testid="`coverage-analysis-${insight.id}`"
              :data-conclusion="insight.结论状态"
            >
              <td>{{ insight.结果编号 }}</td>
              <td data-testid="analysis-fraction">{{ insight.分子 }}/{{ insight.分母 }}</td>
              <td>{{ insight.高分占比 }}</td>
              <td>{{ insight.预测批次 }}</td>
              <td>{{ insight.采用分区.join('、') || '—' }}</td>
              <td>{{ insight.缺失分区.join('、') || '—' }}</td>
              <td>{{ insight.覆盖状态 }}</td>
              <td>
                <span :data-conclusion="insight.结论状态">{{ insight.结论状态 }}</span>
              </td>
              <td>{{ insight.预计行数 }}</td>
              <td>
                <button class="link" type="button" :data-testid="`coverage-evidence-${insight.id}`" @click="openEvidence(insight.id)">
                  原据回查
                </button>
              </td>
            </tr>
            <tr v-if="!analyses.length">
              <td colspan="10" class="empty-state">本轮尚无已完成的覆盖分析</td>
            </tr>
          </tbody>
        </table>

        <div v-if="evidence" class="coverage-evidence" data-testid="coverage-evidence">
          <h3>原据回查 · {{ evidence.insight.结果编号 }}</h3>
          <p>
            分子 {{ evidence.score.numerator }} / 分母 {{ evidence.score.denominator }}
            （{{ evidence.score.ratio }}），采用分区 {{ evidence.partitions.join('、') || '—' }}，
            缺失分区 {{ evidence.missing_partitions.join('、') || '无' }}。
          </p>
          <ul>
            <li v-for="receipt in evidence.receipts" :key="receipt.receipt_id">
              {{ receipt.receipt_id }} · 分片 {{ receipt.shard_id }} · v{{ receipt.version }} ·
              {{ receipt.status }} · {{ receipt.row_count ?? '无行数' }} 行 · {{ receipt.delivery }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  loadCoverage,
  loadCoverageEvidence,
  listCoverageAnalyses,
  listCoverageBatches,
  submitCoverageAnalysis,
  submitReceipt,
  type CoverageEvidence,
} from '@/api/backend-service'
import type {
  CoverageBatchSummary,
  CoverageInsight,
  CoverageSnapshot,
} from '@/data/types'

const batches = ref<CoverageBatchSummary[]>([])
const activeBatchId = ref<number | null>(null)
const snapshot = ref<CoverageSnapshot | null>(null)
const analyses = ref<CoverageInsight[]>([])
const errorMessage = ref('')
const submitting = ref(false)
const submittingReceipt = ref(false)
const analysisNotice = ref<{ message: string; waiting: boolean } | null>(null)
const receiptNotice = ref('')
const evidence = ref<CoverageEvidence | null>(null)

type ReceiptRowInput = { rowKey: string; score: string }
const receiptForm = ref({
  shardId: '',
  status: '已确认',
  note: '',
  rows: [{ rowKey: '', score: '' }] as ReceiptRowInput[],
})

const stateText = computed(() => {
  const state = snapshot.value?.coverage_state
  if (state === '完整') return '全部分片已确认，结论可覆盖整批'
  if (state === '受限') return '已有可用比例，但仍有分片缺回执，结论受限'
  if (state === '等待中') return '尚无已确认回执，本轮仍在等待'
  return '该批次没有分片回执'
})

async function reload() {
  errorMessage.value = ''
  try {
    batches.value = await listCoverageBatches()
    const target = activeBatchId.value
      ?? batches.value.find((batch) => batch.shard_count > 0)?.batch_id
      ?? batches.value[0]?.batch_id
    if (target !== undefined) await selectBatch(target)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '覆盖视图读取失败'
  }
}

async function selectBatch(batchId: number) {
  activeBatchId.value = batchId
  evidence.value = null
  analysisNotice.value = null
  receiptNotice.value = ''
  try {
    snapshot.value = await loadCoverage(batchId)
    analyses.value = await listCoverageAnalyses(batchId)
    const shardIds = snapshot.value.shards.map((shard) => shard.shard_id)
    if (!shardIds.includes(receiptForm.value.shardId)) {
      const next = snapshot.value.shards.find((shard) => !shard.confirmed)
        ?? snapshot.value.shards[0]
      receiptForm.value.shardId = next?.shard_id ?? ''
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '覆盖视图读取失败'
  }
}

function addReceiptRow() {
  receiptForm.value.rows.push({ rowKey: '', score: '' })
}

function removeReceiptRow(index: number) {
  if (receiptForm.value.rows.length === 1) return
  receiptForm.value.rows.splice(index, 1)
}

async function submitReceiptForm() {
  if (activeBatchId.value === null || !receiptForm.value.shardId) return
  submittingReceipt.value = true
  errorMessage.value = ''
  receiptNotice.value = ''
  try {
    const values: Record<string, unknown> = {
      shard_id: receiptForm.value.shardId,
      status: receiptForm.value.status,
      note: receiptForm.value.note,
    }
    if (receiptForm.value.status === '已确认') {
      values.rows = receiptForm.value.rows
        .filter((row) => row.rowKey.trim())
        .map((row) => ({
          row_key: row.rowKey.trim(),
          score: row.score === '' ? null : Number(row.score),
        }))
    }
    const result = await submitReceipt(activeBatchId.value, values)
    if (!result.ok) throw new Error(result.message)
    receiptNotice.value = result.message
    receiptForm.value.rows = [{ rowKey: '', score: '' }]
    receiptForm.value.note = ''
    await selectBatch(activeBatchId.value)
    receiptNotice.value = result.message
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回执登记失败'
  } finally {
    submittingReceipt.value = false
  }
}

async function submitAnalysis() {
  if (activeBatchId.value === null) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const result = await submitCoverageAnalysis(activeBatchId.value)
    await selectBatch(activeBatchId.value)
    analysisNotice.value = {
      message: result.message,
      waiting: Boolean(result.waiting ?? result.entry?.waiting),
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分析提交失败'
  } finally {
    submitting.value = false
  }
}

async function openEvidence(resultId: number) {
  try {
    evidence.value = await loadCoverageEvidence(resultId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '原据回查失败'
  }
}

onMounted(reload)
</script>

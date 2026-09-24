<template>
  <section class="page" data-module="quality">
    <header class="page-head">
      <div>
        <h2>质检管理管理</h2>
        <p class="page-desc">维护质检单，围绕质检单号、关联批次、检测项目、检测值做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记质检单</button>
        <button class="btn" type="button" @click="exportRows">导出质检管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="submitSearch">
      <label class="filter-item">
        <span>质检单号</span>
        <input v-model="form.keyword" placeholder="按质检单号检索" />
      </label>
      <label class="filter-item">
        <span>检测项目</span>
        <input v-model="form.itemName" placeholder="如：中心温度" />
      </label>
      <label class="filter-item">
        <span>检测结论</span>
        <select v-model="form.conclusion">
          <option value="">全部结论</option>
          <option v-for="item in conclusions" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>检测员</span>
        <input v-model="form.inspector" placeholder="按检测员检索" />
      </label>
      <label class="filter-item filter-range">
        <span>检测时间</span>
        <span class="range-inputs">
          <input v-model="form.beginTime" type="date" aria-label="检测开始时间" />
          <em>至</em>
          <input v-model="form.endTime" type="date" aria-label="检测结束时间" />
        </span>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!loading && !rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条质检管理记录</span>
      <div v-if="totalPages > 1" class="pager">
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="goPage(page - 1)">上一页</button>
        <button
          v-for="target in pageNumbers"
          :key="target"
          class="btn"
          :class="{ primary: target === page }"
          type="button"
          :disabled="loading"
          @click="goPage(target)"
        >
          {{ target }}
        </button>
        <button class="btn" type="button" :disabled="page >= totalPages || loading" @click="goPage(page + 1)">下一页</button>
        <span class="pager-tip">第 {{ page }} / {{ totalPages }} 页</span>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

interface QueryParams {
  keyword: string
  itemName: string
  conclusion: string
  inspector: string
  beginTime: string
  endTime: string
}

interface AppliedQuery extends QueryParams {
  page: number
  size: number
}

const ENDPOINT = '/api/quality'
const PAGE_SIZE = 10
const columns = ["质检单号", "关联批次", "检测项目", "检测值", "标准限值", "检测结论", "检测员", "检测时间"]
const actions = ["开始检测", "判定合格", "判定不合格"]
const conclusions = ["合格", "不合格", "待复检"]
const stats = [{"label": "待检批次", "value": 0}, {"label": "检测合格率", "value": 0}, {"label": "不合格批次", "value": 0}]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const errorMessage = ref('')

const emptyForm = (): QueryParams => ({
  keyword: '',
  itemName: '',
  conclusion: '',
  inspector: '',
  beginTime: '',
  endTime: '',
})

const form = reactive<QueryParams>(emptyForm())
// 最近一次生效的查询；条件非法或请求失败时，列表始终回退到这份结果
const applied = ref<AppliedQuery>({ ...emptyForm(), page: 1, size: PAGE_SIZE })
let appliedSignature = ''

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / applied.value.size)))
const hasActiveFilter = computed(() =>
  Object.values(form).some((value) => value.trim() !== ''),
)
const emptyText = computed(() =>
  hasActiveFilter.value
    ? '没有符合当前检索条件的质检记录，请调整或清空条件后重试'
    : '暂无质检管理数据，可先登记质检单',
)
const pageNumbers = computed(() => {
  const pages: number[] = []
  const last = totalPages.value
  const start = Math.max(1, Math.min(page.value - 2, last - 4))
  for (let target = start; target <= Math.min(last, start + 4); target += 1) {
    pages.push(target)
  }
  return pages
})

function validate(input: QueryParams): string {
  const datePattern = /^\d{4}-\d{2}-\d{2}$/
  if (input.beginTime && !datePattern.test(input.beginTime)) {
    return `检测开始时间无效：${input.beginTime}，请选择合法日期`
  }
  if (input.endTime && !datePattern.test(input.endTime)) {
    return `检测结束时间无效：${input.endTime}，请选择合法日期`
  }
  if (input.beginTime && input.endTime && input.beginTime > input.endTime) {
    return '检测开始时间不能晚于结束时间，请调整时间区间'
  }
  if (input.conclusion && !conclusions.includes(input.conclusion)) {
    return `检测结论无效：${input.conclusion}，请选择全部、合格、不合格或待复检`
  }
  return ''
}

function cleanParams(input: QueryParams): QueryParams {
  return {
    keyword: input.keyword.trim(),
    itemName: input.itemName.trim(),
    conclusion: input.conclusion.trim(),
    inspector: input.inspector.trim(),
    beginTime: input.beginTime.trim(),
    endTime: input.endTime.trim(),
  }
}

function buildQuery(params: AppliedQuery): URLSearchParams {
  const search = new URLSearchParams()
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.itemName) search.set('item_name', params.itemName)
  if (params.conclusion) search.set('conclusion', params.conclusion)
  if (params.inspector) search.set('inspector', params.inspector)
  if (params.beginTime) search.set('begin_time', params.beginTime)
  // 结束时间只选日期时包含当天全天
  if (params.endTime) search.set('end_time', `${params.endTime} 23:59:59`)
  search.set('page', String(params.page))
  search.set('size', String(params.size))
  return search
}

function signatureOf(params: AppliedQuery): string {
  return JSON.stringify(params)
}

async function fetchList(params: AppliedQuery) {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery(params).toString()}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail ?? `质检单列表读取失败（${response.status}）`)
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    page.value = payload.page ?? params.page
    applied.value = { ...params }
    appliedSignature = signatureOf(params)
    syncRouteQuery(params)
  } catch (error) {
    // 条件非法或请求失败：说明原因，并保持上一次查询结果不动
    errorMessage.value = error instanceof Error ? error.message : '质检管理列表读取失败'
  } finally {
    loading.value = false
  }
}

function syncRouteQuery(params: AppliedQuery) {
  const query: Record<string, string> = {}
  if (params.keyword) query.keyword = params.keyword
  if (params.itemName) query.itemName = params.itemName
  if (params.conclusion) query.conclusion = params.conclusion
  if (params.inspector) query.inspector = params.inspector
  if (params.beginTime) query.beginTime = params.beginTime
  if (params.endTime) query.endTime = params.endTime
  if (params.page > 1) query.page = String(params.page)
  void router.replace({ name: 'quality', query })
}

function submitSearch() {
  const params = cleanParams(form)
  const reason = validate(params)
  if (reason) {
    // 条件无效：提示原因，列表继续展示上一次的查询结果
    errorMessage.value = reason
    return
  }
  void fetchList({ ...params, page: 1, size: applied.value.size })
}

function goPage(target: number) {
  if (target < 1 || target > totalPages.value || target === page.value) return
  void fetchList({ ...applied.value, page: target })
}

function resetFilters() {
  Object.assign(form, emptyForm())
  void fetchList({ ...emptyForm(), page: 1, size: applied.value.size })
}

function paramsFromRoute(): AppliedQuery {
  const pick = (key: string) => {
    const value = route.query[key]
    return String(Array.isArray(value) ? value[0] ?? '' : value ?? '').trim()
  }
  return {
    keyword: pick('keyword'),
    itemName: pick('itemName'),
    conclusion: pick('conclusion'),
    inspector: pick('inspector'),
    beginTime: pick('beginTime'),
    endTime: pick('endTime'),
    page: Number(pick('page')) || 1,
    size: PAGE_SIZE,
  }
}

async function restoreFromRoute() {
  const candidate = paramsFromRoute()
  Object.assign(form, {
    keyword: candidate.keyword,
    itemName: candidate.itemName,
    conclusion: candidate.conclusion,
    inspector: candidate.inspector,
    beginTime: candidate.beginTime,
    endTime: candidate.endTime,
  })
  const reason = validate(candidate)
  if (reason) {
    // 地址栏里带了非法条件：说明原因，按无条件查询兜底
    errorMessage.value = reason
    Object.assign(form, emptyForm())
    await fetchList({ ...emptyForm(), page: 1, size: PAGE_SIZE })
    return
  }
  await fetchList(candidate)
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '质检单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('质检管理动作未生效，请稍后重试')
    }
    await fetchList({ ...applied.value })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '质检管理操作失败'
  }
}

// 浏览器前进/后退时，按地址栏里的条件重新加载；自己触发的 replace 已生效则跳过
watch(
  () => route.query,
  () => {
    const candidate = paramsFromRoute()
    if (signatureOf(candidate) === appliedSignature) return
    void restoreFromRoute()
  },
)

onMounted(restoreFromRoute)
</script>

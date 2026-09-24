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

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>质检单号</span>
        <input v-model="draft.keyword" placeholder="按质检单号检索" />
      </label>
      <label class="filter-item">
        <span>检测项目</span>
        <input v-model="draft.project" placeholder="如：中心温度、微生物" />
      </label>
      <label class="filter-item">
        <span>检测结论</span>
        <select v-model="draft.conclusion">
          <option value="">全部结论</option>
          <option value="合格">合格</option>
          <option value="不合格">不合格</option>
        </select>
      </label>
      <label class="filter-item">
        <span>检测员</span>
        <input v-model="draft.inspector" placeholder="按检测员检索" />
      </label>
      <label class="filter-item">
        <span>检测时间起</span>
        <input v-model="draft.start_time" type="date" />
      </label>
      <label class="filter-item">
        <span>检测时间止</span>
        <input v-model="draft.end_time" type="date" />
      </label>
      <button class="btn primary" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="errorMessage" class="error-banner" role="alert">{{ errorMessage }}</p>

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
      <span>共 {{ total }} 条质检管理记录，第 {{ page }} / {{ totalPages }} 页</span>
      <nav class="pagination" aria-label="质检列表分页">
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="goPage(1)">首页</button>
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
      </nav>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Filters = {
  keyword: string
  project: string
  conclusion: string
  inspector: string
  start_time: string
  end_time: string
}

const ENDPOINT = '/api/quality'
const PAGE_SIZE = 10
const columns = ["质检单号", "关联批次", "检测项目", "检测值", "标准限值", "检测结论", "检测员", "检测时间"]
const actions = ["开始检测", "判定合格", "判定不合格"]
const stats = [{"label": "待检批次", "value": 0}, {"label": "检测合格率", "value": 0}, {"label": "不合格批次", "value": 0}]

// 模块级状态：翻到别的菜单再回来时，保留上一次的检索条件、页码与结果。
// Vue Router 离开页面时不会销毁 <script setup> 的模块作用域，组件卸载后这些值仍在。
const cache: {
  draft: Filters
  applied: Filters
  page: number
  rows: Row[]
  total: number
  loaded: boolean
} = {
  draft: { keyword: '', project: '', conclusion: '', inspector: '', start_time: '', end_time: '' },
  applied: { keyword: '', project: '', conclusion: '', inspector: '', start_time: '', end_time: '' },
  page: 1,
  rows: [],
  total: 0,
  loaded: false,
}

const draft = reactive<Filters>({ ...cache.draft })
const appliedFilters = reactive<Filters>({ ...cache.applied })
const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const errorMessage = ref('')

// 初始化时还原上一次离开前列表（条件、页码、结果都来自缓存）。
rows.value = cache.rows
total.value = cache.total
page.value = cache.page

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasActiveFilters = computed(() => Object.values(appliedFilters).some((value) => value.trim() !== ''))
const emptyText = computed(() =>
  hasActiveFilters.value
    ? '没有符合当前检索条件的质检记录，请调整检测项目、结论、检测员或检测时间区间后重试'
    : '暂无质检管理数据，可先登记质检单',
)
const pageNumbers = computed(() => {
  const last = totalPages.value
  const start = Math.max(1, Math.min(page.value - 2, last - 4))
  return Array.from({ length: Math.min(5, last) }, (_, index) => start + index).filter((target) => target <= last)
})

function persistState() {
  ;(Object.keys(cache.draft) as (keyof Filters)[]).forEach((key) => {
    cache.draft[key] = draft[key]
    cache.applied[key] = appliedFilters[key]
  })
  cache.page = page.value
  cache.rows = rows.value
  cache.total = total.value
}

function buildQuery(targetPage: number) {
  const params = new URLSearchParams()
  ;(Object.keys(appliedFilters) as (keyof Filters)[]).forEach((key) => {
    const value = appliedFilters[key].trim()
    if (value) {
      params.set(key, value)
    }
  })
  params.set('page', String(targetPage))
  params.set('size', String(PAGE_SIZE))
  return params.toString()
}

function validateFilters(filters: Filters): string {
  const datePattern = /^\d{4}-\d{2}-\d{2}$/
  const start = filters.start_time.trim()
  const end = filters.end_time.trim()
  if (start && !datePattern.test(start)) {
    return '检测时间起填写无效，请选择或填写 YYYY-MM-DD 格式的日期'
  }
  if (end && !datePattern.test(end)) {
    return '检测时间止填写无效，请选择或填写 YYYY-MM-DD 格式的日期'
  }
  if (start && end && start > end) {
    return '检测时间区间无效：开始时间不能晚于结束时间'
  }
  return ''
}

async function fetchPage(targetPage: number) {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery(targetPage)}`)
    if (response.status === 400) {
      const payload = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(payload?.detail || '检索条件无效，请检查后重试')
    }
    if (!response.ok) {
      throw new Error('质检单列表读取失败')
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    page.value = targetPage
    // 条件有效但落在空页（如翻页期间数据变化）：回到最后一页再查一次。
    if (!rows.value.length && total.value > 0 && targetPage > 1) {
      const lastPage = Math.max(1, Math.ceil(total.value / PAGE_SIZE))
      loading.value = false
      await fetchPage(lastPage)
      return
    }
    cache.loaded = true
  } catch (error) {
    // 条件无效或请求失败：保留上一次的查询结果与页码，只提示原因。
    errorMessage.value = error instanceof Error ? error.message : '质检管理列表读取失败'
  } finally {
    loading.value = false
    persistState()
  }
}

function applyFilters() {
  const reason = validateFilters(draft)
  if (reason) {
    errorMessage.value = reason
    return
  }
  ;(Object.keys(appliedFilters) as (keyof Filters)[]).forEach((key) => {
    appliedFilters[key] = draft[key].trim()
  })
  void fetchPage(1)
}

function resetFilters() {
  ;(Object.keys(draft) as (keyof Filters)[]).forEach((key) => {
    draft[key] = ''
    appliedFilters[key] = ''
  })
  errorMessage.value = ''
  void fetchPage(1)
}

function goPage(target: number) {
  if (target < 1 || target > totalPages.value || target === page.value) {
    return
  }
  void fetchPage(target)
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
    await fetchPage(page.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '质检管理操作失败'
  }
}

onMounted(() => {
  // 从其他页面返回时沿用上次的检索条件、页码与结果；尚未成功加载过时先拉取首页。
  if (cache.loaded) {
    return
  }
  void fetchPage(1)
})
</script>

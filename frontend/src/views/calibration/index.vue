<template>
  <section class="page" data-module="calibration">
    <header class="page-head">
      <div>
        <h2>设备标定管理</h2>
        <p class="page-desc">维护标定记录，围绕标定编号、标定对象、标定机构、标定项目做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记标定记录</button>
        <button class="btn" type="button" @click="exportRows">导出设备标定清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>标定编号</span>
        <input v-model="keyword" placeholder="按标定编号检索" />
      </label>
      <label class="filter-item">
        <span>标定状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '标定编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actionsFor(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!actionsFor(row).length" class="muted-text">已办结</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无设备标定数据，可先登记标定记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条设备标定记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="createVisible" class="dialog-mask" @click.self="createVisible = false">
      <form class="dialog" @submit.prevent="submitCreate">
        <h3 class="dialog-title">登记标定记录</h3>
        <label v-for="field in createFields" :key="field.name" class="dialog-item">
          <span>{{ field.name }}<em v-if="field.required" class="required-mark">*</em></span>
          <input v-model="createForm[field.name]" :placeholder="field.required ? '必填' : '选填'" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="dialog-actions">
          <button class="btn primary" type="submit">提交登记</button>
          <button class="btn ghost" type="button" @click="createVisible = false">取消</button>
        </div>
      </form>
    </div>

    <div v-if="detail" class="dialog-mask" @click.self="detail = null">
      <section class="dialog">
        <h3 class="dialog-title">标定记录详情</h3>
        <dl class="detail-list">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] || '—' }}</dd>
          </template>
        </dl>
        <div class="dialog-actions">
          <button class="btn ghost" type="button" @click="detail = null">关闭</button>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatItem = { label: string; value: number }

const ENDPOINT = '/api/calibration'
const columns = ["标定编号", "标定对象", "标定机构", "标定项目", "标定结论", "有效期至", "标定人员", "标定状态"]
const statuses = ["待送检", "标定中", "标定合格", "标定不合格"]
// 状态机与后端一致：待送检 → 标定中 → 标定合格 / 标定不合格，终态不再给动作。
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  '待送检': ['送检登记'],
  '标定中': ['确认合格', '判定不合格'],
}
const createFields = [
  { name: '标定编号', required: true },
  { name: '标定对象', required: true },
  { name: '标定机构', required: true },
  { name: '标定项目', required: false },
  { name: '标定人员', required: false },
]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatItem[]>([
  { label: '待送检设备', value: 0 },
  { label: '标定合格', value: 0 },
  { label: '标定不合格', value: 0 },
  { label: '超期未标定', value: 0 },
])
const errorMessage = ref('')
const noticeMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const createVisible = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})
const detail = ref<Row | null>(null)

function actionsFor(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row.status ?? row['标定状态'] ?? '')] ?? []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createError.value = ''
  createVisible.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      createError.value = payload.message ?? '标定记录登记失败，请检查填写内容'
      return
    }
    createVisible.value = false
    noticeMessage.value = payload.message ?? '标定记录已登记'
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '标定记录登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      errorMessage.value = payload.message ?? `标定记录${action}未生效`
      return
    }
    noticeMessage.value = payload.message ?? `标定记录已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '设备标定操作失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    const payload = await response.json()
    if (!response.ok) {
      errorMessage.value = payload.detail ?? `标定记录 ${row.id} 读取失败`
      return
    }
    detail.value = payload
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '标定记录详情读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error('标定记录列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const statsPayload = await statsResponse.json()
      stats.value = statsPayload.stats ?? stats.value
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '设备标定列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.muted-text { color: var(--muted); font-size: 12px; }
.notice-text { color: #027a48; }
.dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}
.dialog {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  width: 380px;
  max-height: 80vh;
  overflow: auto;
}
.dialog-title { margin: 0 0 12px; font-size: 15px; }
.dialog-item { display: block; margin-bottom: 10px; }
.dialog-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.dialog-item input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
}
.required-mark { color: #b42318; font-style: normal; margin-left: 2px; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.detail-list { display: grid; grid-template-columns: 96px 1fr; gap: 6px 12px; margin: 0; }
.detail-list dt { color: var(--muted); font-size: 13px; }
.detail-list dd { margin: 0; font-size: 13px; }
</style>

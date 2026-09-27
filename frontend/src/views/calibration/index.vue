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
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无设备标定数据，可先登记标定记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条设备标定记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="createVisible" class="dialog-mask" @click.self="createVisible = false">
      <div class="dialog">
        <h3>登记标定记录</h3>
        <form class="dialog-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.name">
            <span>{{ field.name }}{{ field.required ? '（必填）' : '' }}</span>
            <input v-model="createForm[field.name]" :placeholder="`请填写${field.name}`" />
          </label>
          <p v-if="createError" class="error-text">{{ createError }}</p>
          <div class="dialog-actions">
            <button class="btn ghost" type="button" @click="createVisible = false">取消</button>
            <button class="btn primary" type="submit">提交登记</button>
          </div>
        </form>
      </div>
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
const actions = ["送检登记", "确认合格", "判定不合格"]
const statuses = ["待送检", "标定中", "标定合格", "标定不合格"]
const createFields = [
  { name: '标定编号', required: true },
  { name: '标定对象', required: true },
  { name: '标定机构', required: true },
  { name: '标定项目', required: false },
  { name: '标定人员', required: false },
]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatItem[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const createVisible = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})

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

async function readPayload(response: Response): Promise<Record<string, unknown>> {
  try {
    return (await response.json()) as Record<string, unknown>
  } catch {
    return {}
  }
}

async function backendMessage(response: Response, fallback: string): Promise<string> {
  const payload = await readPayload(response)
  if (typeof payload.message === 'string' && payload.message) return payload.message
  if (typeof payload.detail === 'string' && payload.detail) return payload.detail
  return response.ok ? fallback : `${fallback}（接口返回 ${response.status}）`
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await readPayload(response)
    if (!response.ok || payload.ok === false) {
      createError.value = typeof payload.message === 'string' && payload.message
        ? payload.message
        : `标定记录登记未生效（接口返回 ${response.status}）`
      return
    }
    createVisible.value = false
    noticeMessage.value = typeof payload.message === 'string' ? payload.message : '标定记录已登记'
    await Promise.all([reload(), loadStats()])
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
    const payload = await readPayload(response)
    if (!response.ok || payload.ok === false) {
      errorMessage.value = typeof payload.message === 'string' && payload.message
        ? payload.message
        : `设备标定动作未生效（接口返回 ${response.status}）`
      return
    }
    noticeMessage.value = typeof payload.message === 'string' ? payload.message : `标定记录已${action}`
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '设备标定操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error(await backendMessage(response, '标定记录列表读取失败'))
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '设备标定列表读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = await response.json()
    stats.value = payload.items ?? []
  } catch {
    // 统计卡片加载失败不阻断列表操作
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

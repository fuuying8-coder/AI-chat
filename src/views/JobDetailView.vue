<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getJobDetail } from '@/utils/api'
import { ArrowLeft, Expand, RefreshRight, Document } from '@element-plus/icons-vue'



interface TableRow {
  rowType: 'commit' | 'job'

  commitId: string
  taskId: number | string
  crId: number | string
  crName?: string
  mergeTime?: string
  createTime?: string

  jobId?: number | string
  runStatus?: string
  reportId?: number | string

  metrics: Record<string, WatchMetricValue>

  parentCommitId?: string
  expanded?: boolean
  _rowKey?: string
}

interface WatchMetricItem {
  category: string
  name: string
  sub_category?: string      // plugin 专用，与 row.metrics 的 key 格式一致
}

interface WatchMetricValue {
  p90?: string | number | null
  p99?: string | number | null
  max?: string | number | null
}


const mockJobDetail = ref ({
  job: {
    id: 3,
    create_time: '2026-01-20T15:27:21+08:00',
    update_time: '2026-01-20T15:27:21+08:00',
    username: 'oliverwang',
    job_name: 'test_job_1234567890',
    reproduce_platform: 1,
    reproduce_env: 0,
    reproduce_node: 0,
    reproduce_scenario: 'perf_test_gating_17129',
    addition_args:
      'diff_package_source=BUILD_IN_CLOUD&running_nodes=voy-onboard-thor2-node.service&node_latency_type=PredictionPlanner',
    start_commit_id: '6712500faad359390e14f225e909989e57d18e80',
    end_commit_id: '6712500faad359390e14f225e909989e57d18e68',
    watch_metric:
       "{\"latency\":[\"planning_node\",\"sensing_node\"],\"trace\":[\"CurbDetector_Voxelize\"],\"plugin\":{\"message_size_plugin\":[\"fallback_planning_trajectory\"]}}",
    reproduce_step: 2,
  },
  task_list: [
    {
      id: 1,
      create_time: '2026-01-20T15:27:50+08:00',
      update_time: '2026-01-20T20:07:56+08:00',
      merge_time: '2025-09-24T16:41:17+08:00',
      commit_id: '10ba71ef137715332bc722ae6552d1a63ce2aed6',
      reproduce_status: 2,
      result: 0,
      cr_id: 4339743,
      regression_job_id: 3,
      reproduce_job_list: '[63017,63019,63021]',
    },
    {
      id: 3,
      create_time: '2026-01-20T15:27:50+08:00',
      update_time: '2026-01-20T15:27:50+08:00',
      merge_time: '2025-08-15T20:23:02+08:00',
      commit_id: '6712500faad359390e14f225e909989e57d18e70',
      reproduce_status: 0,
      result: 0,
      cr_id: 5181917,
      regression_job_id: 3,
      reproduce_job_list: '',
    },
    {
      id: 5,
      create_time: '2026-01-20T15:27:50+08:00',
      update_time: '2026-01-20T15:27:50+08:00',
      merge_time: '2025-01-15T20:23:02+08:00',
      commit_id: '6712500faad359390e14f225e909989e57d18e68',
      reproduce_status: 0,
      result: 0,
      cr_id: 4181917,
      regression_job_id: 3,
      reproduce_job_list: '',
    },
    {
      id: 7,
      create_time: '2026-01-20T15:27:50+08:00',
      update_time: '2026-01-20T20:07:57+08:00',
      merge_time: '2025-01-15T20:11:01+08:00',
      commit_id: '1f7129e0b568a074522f21bd6b4fc5aac5678ea8',
      reproduce_status: 2,
      result: 0,
      cr_id: 4401223,
      regression_job_id: 3,
      reproduce_job_list: '[63015,63023]',
    },
  ],
})
const route = useRoute()
const id = computed(() => route.params.id || '')
const regressionJobDetail = ref(null)
const tableRows = ref<TableRow[]>([])
const expandedCommitIds = ref<Set<string>>(new Set())

async function loadDetail() {
  try {
    // await regressionStore.getRegressionJobDetail(Number(id.value))
    // regressionJobDetail.value = regressionStore.regressionJobDetail
    regressionJobDetail.value =  { job: mockJobDetail.value.job, task_list: mockJobDetail.value.task_list }
    buildTableRows()
  } catch (e) {
    error.value = e.message || '加载失败'
    regressionJobDetail.value = null
    tableRows.value = []
  } finally {
    loading.value = false
  }
}

function buildTableRows() {
  const tasks = regressionJobDetail.value?.task_list || []
  const rows: TableRow[] = []

  // 1. 先按 commit 分组
  const commitMap: Record<string, any[]> = {}
  tasks.forEach(task => {
    if (!commitMap[task.commit_id]) {
      commitMap[task.commit_id] = []
    }
    commitMap[task.commit_id].push(task)
  })

  // 2. commit 排序（merge_time 倒序）
  const sortedCommits = Object.keys(commitMap).sort((a, b) => {
    const ma = commitMap[a][0].merge_time
    const mb = commitMap[b][0].merge_time
    return new Date(mb).getTime() - new Date(ma).getTime()
  })

  // 3. 构建行
  sortedCommits.forEach(commitId => {
    const task = commitMap[commitId][0]

    // —— commit 母行
    rows.push({
      rowType: 'commit',
      commitId,
      taskId: task.id,
      crId: task.cr_id,
      createTime: task.create_time,
      mergeTime: task.merge_time,
      metrics: {},
      expanded: true,
      _rowKey: `commit-${task.id}`,
    })

    // —— job 子行
    const jobs = task.reproduce_job_list
      ? JSON.parse(task.reproduce_job_list)
      : []

    jobs.forEach((jobId: number) => {
      rows.push({
        rowType: 'job',
        parentCommitId: commitId,
        commitId,
        taskId: task.id,
        crId: task.cr_id,
        jobId,
        metrics: {},
        _rowKey: `job-${task.id}-${jobId}`,
      })
    })
  })

  tableRows.value = rows
  // 有子行的 commit 默认展开
  const ids = new Set<string>()
  rows.forEach((row) => {
    if (row.rowType === 'job' && row.parentCommitId) ids.add(row.parentCommitId)
  })
  expandedCommitIds.value = ids
}

const allMetrics = computed(() => {
  const watchMetric = regressionJobDetail.value?.job?.watch_metric
  return parseWatchMetricToItems(watchMetric)
})

// 每个指标的唯一 key，与 row.metrics[key] 对应（plugin 为 category:sub_category:name，否则 category:name）
function getMetricKey(item: { category: string; name: string; sub_category?: string }) {
  if (item.sub_category) return `${item.category}:${item.sub_category}:${item.name}`
  return `${item.category}:${item.name}`
}

// 从 watch_metric 解析为 allMetrics（展平为 category + name，plugin 展平为 category + sub_category + name）
function parseWatchMetricToItems(watchMetricStr) {
  if (!watchMetricStr || typeof watchMetricStr !== 'string') return []
  try {
    const obj = JSON.parse(watchMetricStr.trim())
    if (!obj || typeof obj !== 'object') return []
    const list = []
    for (const category of Object.keys(obj)) {
      const val = obj[category]
      if (Array.isArray(val)) {
        val.forEach((name) => list.push({ category, name }))
      } else if (val && typeof val === 'object') {
        // plugin: { message_size_plugin: ["fallback_planning_trajectory"] }
        for (const sub_category of Object.keys(val)) {
          const names = val[sub_category]
          if (Array.isArray(names)) {
            names.forEach((name) => list.push({ category, sub_category, name }))
          }
        }
      }
    }
    return list.length ? list : []
  } catch {
    return []
  }
}

// 每个指标单元格内三个值的展示格式：{ p90, p99, max } -> 三行 "P90: 20ms" / "P99: 19ms" / "Max: 22ms"
function formatMetricCell(val) {
  if (val == null) return ''
  if (typeof val === 'string' || typeof val === 'number') return String(val)
  const p90 = val.p90 != null ? `P90: ${val.p90}` : ''
  const p99 = val.p99 != null ? `P99: ${val.p99}` : ''
  const max = val.max != null ? `Max: ${val.max}` : ''
  const parts = [p90, p99, max].filter(Boolean)
  return parts.length ? parts.join('\n') : '-'
}

onMounted(async () => {
  await loadDetail()
  await fetchCrNames()
  await fetchRunStatus()
  await fetchReportId()
  await fetchAndFillMetricsForRows(tableRows.value, allMetrics.value)
})

async function fetchCrNames() {
  const commitRows = tableRows.value.filter(r => r.rowType === 'commit')

  for (const row of commitRows) {
      // row.crName = await taskDetailStore.getCrTitleHandle(String(row.crId))
      row.crName = '1234' + row.crId
  }
}

async function fetchRunStatus() {
  const jobRows = tableRows.value.filter(r => r.rowType === 'job')

  for (const row of jobRows) {
    // const res = await fetchJobDetail(row.jobId!)
    const statusArr = [
      { test_status: '1', text: '已成功' },
      { test_status: '2', text: '进行中' },
    ]
    const res = statusArr[Math.floor(Math.random() * statusArr.length)]
    row.runStatus = res.text
  }
}

async function fetchReportId() {
  const jobRows = tableRows.value.filter((r) => r.rowType === 'job')
  for (const row of jobRows) {
    // const res = await fetchJobReportFull({ id: row.jobId })
    // row.reportId = getBaseReportId(res.data.data.report_list)
    row.reportId = row.jobId
  }
}


async function fetchAndFillMetricsForRows(
  tableRows: TableRow[],
  allMetrics: WatchMetricItem[]
) {
  if (!tableRows.length || !allMetrics.length) return

  // 先把指标按 category 分组（只用于调接口）
  let metricsByCategory: Record<string, WatchMetricItem[]> = {}

  // allMetrics.forEach(m => {
  //   if (!metricsByCategory[m.category]) {
  //     metricsByCategory[m.category] = []
  //   }
  //   metricsByCategory[m.category].push(m)
  // })

  metricsByCategory = {
	  'latency': [
	    { category: 'latency', name: 'planning_node' },
	    { category: 'latency', name: 'sensing_node' },
	  ],
	  'trace': [
	    { category: 'trace', name: 'CurbDetector_Voxelize' },
	  ],
	}

  //  遍历每一行（每个 job）
  for (const row of tableRows) {
    if (!row.reportId) continue

    // 确保 metrics 已初始化
    if (!row.metrics) row.metrics = {}

    //  按 category 查接口
    for (const category of Object.keys(metricsByCategory)) {
      const metricDefs = metricsByCategory[category]

      // 临时写死，方便测试
      // metricDefs = [
			//   { category: 'latency', name: 'planning_node' },
			//   { category: 'latency', name: 'sensing_node' },
			// ]

      console.log('fetch metrics for row:', row.reportId, category)


      let res: any
      try {
        // res = await fetchMetricByReportId({
        //   reportId: row.reportId,
        //   category,
        // })
      } catch (e) {
        console.warn('fetch metric failed:', row.reportId, category)
        continue
      }

      /** 4️⃣ 拿到 category_list */
      // const listKey = `${category}_list`
      // const metricList: any[] = res?.data?.[listKey] || []

      // if (!metricList.length) continue

      // /** 5️⃣ 先构建一个 name -> value 的 Map（提高查找效率） */
      // const metricValueMap: Record<string, WatchMetricValue> = {}

      // metricList.forEach(item => {
      //   const nameKey = `${category}_name`
      //   const p90Key = `${category}_p90`
      //   const p99Key = `${category}_p99`
      //   const maxKey = `${category}_max`

      //   const name = item[nameKey]
      //   if (!name) return

      //   metricValueMap[name] = {
      //     p90: item[p90Key] ?? null,
      //     p99: item[p99Key] ?? null,
      //     max: item[maxKey] ?? null,
      //   }
      // })

      // /** 6️⃣ 写回 row.metrics（拍扁） */
      // metricDefs.forEach(def => {
      //   const key = `${def.category}:${def.name}`
      //   row.metrics[key] =
      //     metricValueMap[def.name] ?? {
      //       p90: null,
      //       p99: null,
      //       max: null,
      //     }
      // })

      metricDefs.forEach((def: WatchMetricItem) => {
        const key = def.sub_category
          ? `${def.category}:${def.sub_category}:${def.name}`
          : `${def.category}:${def.name}`
        row.metrics[key] = {
          p90: 20,
          p99: 25,
          max: 30,
        }
      })
    }
    console.log('filled metrics for row:', row.reportId, row.metrics)
  }
}


const loading = ref(true)
const error = ref('')



function hasJobRows(commitId: string) {
  return tableRows.value.some(
    (r) => r.rowType === 'job' && r.parentCommitId === commitId
  )
}

// 展示用：按 expandedCommitIds 过滤，收起时隐藏该 commit 下的 job 行
const tableRowsDisplay = computed(() => {
  const list = tableRows.value
  const result: TableRow[] = []
  let currentExpanded = false
  for (const row of list) {
    if (row.rowType === 'commit') {
      result.push(row)
      currentExpanded = expandedCommitIds.value.has(row.commitId)
    } else if (row.rowType === 'job' && currentExpanded) {
      result.push(row)
    }
  }
  return result
})

function isCommitExpanded(commitId) {
  return expandedCommitIds.value.has(commitId)
}

function toggleExpand(commitId) {
  const next = new Set(expandedCommitIds.value)
  if (next.has(commitId)) next.delete(commitId)
  else next.add(commitId)
  expandedCommitIds.value = next
}




</script>

<template>
  <div class="job-detail-page">
    <header class="header">
      <router-link to="/" class="back-link">
        <el-icon><ArrowLeft /></el-icon>
        <span>返回</span>
      </router-link>
      <h1 class="title">测试详情</h1>
    </header>

    <div v-if="loading" class="loading-wrap">
      <el-icon class="is-loading"><Expand /></el-icon>
      <span>加载中...</span>
    </div>
    <div v-else-if="error" class="error-wrap">
      <el-alert type="error" :title="error" show-icon />
    </div>
    <template v-else>

      <!-- 回溯测试详情列表 -->
      <section class="table-section">
        <div class="table-header">
          <h2 class="table-title">回溯测试详情列表</h2>
          <div class="table-actions">
            <el-button type="primary">批量重试</el-button>
          </div>
        </div>

        <div class="table-wrap">
          <table class="detail-table">
            <thead>
              <tr>
                <th rowspan="2">Commit ID</th>
                <th rowspan="2">CR Name</th>
                <th rowspan="2">执行批次</th>
                <th rowspan="2">测试创建时间</th>
                <th rowspan="2">运行状态</th>
                <th :colspan="(allMetrics || []).length">关注指标</th>
                <th rowspan="2">复现结果</th>
                <th rowspan="2">重试</th>
                <th rowspan="2">测试报告</th>
              </tr>
              <tr>
                <th v-for="m in (allMetrics || [])" :key="getMetricKey(m)" class="col-metric-sub">
                  <template v-if="m.sub_category">
                    <span class="metric-header-line metric-header-line-1">{{ m.category }}</span>
                    <span class="metric-header-line metric-header-line-2">{{ m.sub_category }}</span>
                    <span class="metric-header-line metric-header-line-3">{{ m.name }}</span>
                  </template>
                  <template v-else>
                    <span class="metric-header-line metric-header-line-1">{{ m.category }}</span>
                    <span class="metric-header-line metric-header-line-3">{{ m.name }}</span>
                  </template>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in tableRowsDisplay" :key="row._rowKey">
                <!-- commitId -->
                <td>
                  <div class="commit-id-cell">
                    <span v-if="row.rowType === 'commit' && hasJobRows(row.commitId)" class="commit-id-left">
                      <span class="expand-box" @click="toggleExpand(row.commitId)" role="button" tabindex="0">
                        <svg class="expand-box-svg" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                          <rect x="1" y="1" width="18" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="1.5" />
                          <line v-if="isCommitExpanded(row.commitId)" x1="5" y1="10" x2="15" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                          <g v-else>
                            <line x1="10" y1="5" x2="10" y2="15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                            <line x1="5" y1="10" x2="15" y2="10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                          </g>
                        </svg>
                      </span>
                    </span>
                    <span v-else-if="row.rowType === 'job'" class="commit-id-left"></span>
                    <span v-if="row.rowType === 'commit'" :title="row.commitId">{{ row.commitId }}</span>
                  </div>
                </td>
                <!-- crName -->
                <td :title="row.rowType === 'commit' ? ( row.crName ?? '-') : ''">
                  <template v-if="row.rowType === 'commit'">{{ row.crName ?? '-' }}</template>
                </td>
                <!-- 批次 -->
                <td>
                  <template v-if="row.rowType === 'job'">{{ row.jobId ?? '' }}</template>
                </td>
                <!-- 创建时间 -->
                <td>{{ row.createTime }}</td>
                <!-- 运行状态 -->
                <td>
                  <template v-if="row.rowType === 'job'">
                      {{  row.runStatus }}
                  </template>
                </td>
                <!-- 关注指标 -->
                <td v-for="m in (allMetrics || [])" :key="getMetricKey(m)" class="col-metric">
                  <span class="metric-cell">{{ formatMetricCell((row.metrics)?.[getMetricKey(m)]) }}</span>
                </td>
                <!-- 复现结果 -->
                <td>
                  <el-select v-if="row.rowType === 'job'" placeholder="请选择" size="small" style="width: 100px">
                    <el-option label="请选择" value="" />
                    <el-option label="通过" value="1" />
                    <el-option label="失败" value="2" />
                  </el-select>
                </td>
                <!-- 重试 -->
                <td>
                  <el-button v-if="row.rowType === 'job'" link type="primary" size="small">
                    <el-icon><RefreshRight /></el-icon>
                    重试
                  </el-button>
                </td>
                <td>
                  <el-button v-if="row.rowType === 'job'" link type="primary" size="small">
                    <el-icon><Document /></el-icon>
                    报告
                  </el-button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.job-detail-page {
  min-height: 100vh;
  background-color: var(--el-bg-color);
  padding-bottom: 40px;
}

.header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--el-border-color);
  display: flex;
  align-items: center;
  gap: 16px;

  .back-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--el-color-primary);
    text-decoration: none;
    font-size: 14px;
    &:hover {
      color: var(--el-color-primary-light-3);
    }
  }

  .title {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }
}

.loading-wrap,
.error-wrap {
  padding: 40px 24px;
  text-align: center;
}

.detail-header {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px 24px 16px;
  background: var(--el-bg-color);

  .detail-title-row {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 12px;
  }

  .detail-title {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }

  .detail-meta {
    color: var(--el-text-color-secondary);
    font-size: 14px;
  }

  .detail-meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    font-size: 13px;
    color: var(--el-text-color-regular);

    span {
      white-space: nowrap;
    }
    strong {
      margin-right: 4px;
      color: var(--el-text-color-secondary);
    }
  }
}

.table-section {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 24px 24px;
}

.table-wrap {
  overflow-x: auto; // 横向滚动
  overflow-y: auto;
  border: 1px solid var(--el-border-color); // 表格边框
  border-radius: 4px;
}

.detail-table {
  width: 100%;
  border-collapse: collapse; // 合并边框
  font-size: 14px;

  thead {
    background: var(--el-fill-color-light);
  }

  th {
    border: 1px solid var(--el-border-color);
    padding: 10px 12px;
    text-align: center;
    font-weight: 600;
  }

  th.col-metric-sub {
    font-weight: 500;
    font-size: 12px;
    width: 40px;
    min-width: 40px;
    vertical-align: middle;
  }

  .metric-header-line {
    display: block;
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .metric-header-line-1 {
    font-size: 14px;
    font-weight: 700;
  }
  .metric-header-line-2 {
    font-size: 13px;
  }
  .metric-header-line-3 {
    font-size: 11px;
  }

  td {
    border: 1px solid var(--el-border-color);
    padding: 10px 12px;
  }

  .commit-id-cell {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  /* 左侧区域：有子行时放展开框(20px)，job 行时放占位与上方对齐 */
  .commit-id-left {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    flex-shrink: 0;
  }

  .col-metric {
    width: 90px;
    min-width: 90px;
    text-align: center;
    vertical-align: middle;
  }

}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.table-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.table-actions {
  display: flex;
  gap: 12px;
}



.expand-box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  cursor: pointer;
  color: var(--el-text-color-regular);
  flex-shrink: 0;
  &:hover {
    color: var(--el-color-primary);
  }
}

.expand-box-svg {
  width: 100%;
  height: 100%;
  display: block;
}


.metric-cell {
  font-size: 12px;
  white-space: pre-wrap;
  line-height: 1.4;
  text-align: center;
  display: inline-block;
}

</style>

/**
 * Upload Task 模块：断点续传 + 并发池 + 状态持久化
 * 流程：计算 hash -> 问后端已存在 chunk -> 只传缺失 -> 通知完成 -> 轮询合并状态
 */

import { sliceAndHash, DEFAULT_CHUNK_SIZE } from './slicer.js'
import { createConcurrencyPool } from './concurrencyPool.js'
import { getTaskState, setTaskState, clearTaskState, UploadStatus } from './uploadState.js'

/** @typedef { 'waiting' | 'uploading' | 'success' | 'failed' } TaskStatus */
/** @typedef { { status: TaskStatus, fileHash: string, fileName: string, totalChunks: number, uploadedChunks: number[], jobId?: string, fileId?: string, error?: string, chunkSize: number } } TaskState */

const DEFAULT_CONCURRENCY = 4
const POLL_INTERVAL_MS = 1500
const POLL_MAX_ATTEMPTS = 120 // 3 min

/**
 * 创建上传任务（可复用：若 state 已存在则恢复）
 * @param {File} file
 * @param {{
 *   backendBaseUrl: string
 *   getAuthHeader?: () => string
 *   chunkSize?: number
 *   concurrency?: number
 *   onProgress?: (state: TaskState) => void
 * }} options
 * @returns {Promise<{ fileId: string, fileName: string }>}
 */
// 创建上传任务，支持断点续传、并发上传和状态持久化
export async function runUploadTask(file, options) {
  // 解构参数，设置默认值
  const {
    backendBaseUrl, // 后端基础 URL
    getAuthHeader = () => '', // 获取鉴权头的方法，默认为空
    chunkSize = DEFAULT_CHUNK_SIZE, // 分片大小，默认值
    concurrency = DEFAULT_CONCURRENCY, // 并发数，默认值
    onProgress, // 进度回调
  } = options

  // 创建并发池控制器
  const run = createConcurrencyPool(concurrency)

  // 1) 切片并计算文件 hash，返回分片信息
  const { fileHash, chunks, totalChunks, fileName, fileSize } = await sliceAndHash(file, { chunkSize })

  // 持久化任务状态并触发进度回调
  const persist = (state) => {
    setTaskState(fileHash, state)
    onProgress?.(state)
  }

  // 尝试恢复已存在的任务状态
  let state = getTaskState(fileHash)
  // 如果已上传成功且有 fileId，直接返回
  if (state && (state.status === UploadStatus.SUCCESS && state.fileId)) {
    return { fileId: state.fileId, fileName: state.fileName }
  }
  // 如果没有状态，初始化任务状态
  if (!state) {
    state = {
      status: UploadStatus.WAITING, // 等待上传
      fileHash,
      fileName,
      totalChunks,
      uploadedChunks: [], // 已上传分片索引
      chunkSize,
    }
    persist(state)
  }

  // 2) 向后端查询已存在的分片，避免重复上传
  const checkRes = await fetch(`${backendBaseUrl}/api/upload/check`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(getAuthHeader() && { Authorization: getAuthHeader() }), // 可选鉴权
    },
    body: JSON.stringify({
      file_hash: fileHash,
      file_name: fileName,
      total_chunks: totalChunks,
      chunk_size: chunkSize,
    }),
  })
  // 检查响应是否正常
  if (!checkRes.ok) {
    const err = await checkRes.json().catch(() => ({}))
    throw new Error(err.error?.message || `check failed: ${checkRes.status}`)
  }
  // 解析后端返回的数据
  const checkData = await checkRes.json()
  // 如果文件已存在且有 file_id，直接返回
  if (checkData.exists && checkData.file_id) {
    state = { ...state, status: UploadStatus.SUCCESS, fileId: checkData.file_id, fileName }
    persist(state)
    return { fileId: checkData.file_id, fileName }
  }
  // 已上传分片集合
  const alreadyUploaded = new Set(checkData.uploaded_chunks || [])

  // 3) 只上传缺失的分片，利用并发池加速
  state.status = UploadStatus.UPLOADING
  persist(state)

  // 过滤出未上传的分片
  const toUpload = chunks.filter((c) => !alreadyUploaded.has(c.index))
  // 定义单个分片上传任务
  const uploadTask = (chunk) => () =>
    uploadOneChunk(backendBaseUrl, getAuthHeader, fileHash, fileName, totalChunks, chunk).then((index) => {
      // 上传成功后，记录已上传分片索引
      state.uploadedChunks = [...(state.uploadedChunks || []), index]
      persist(state)
      return index
    })
  // 并发上传所有未上传分片
  await Promise.all(toUpload.map((chunk) => run(uploadTask(chunk))))

  // 4) 通知后端所有分片上传完成，请合并文件
  const completeRes = await fetch(`${backendBaseUrl}/api/upload/complete`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(getAuthHeader() && { Authorization: getAuthHeader() }),
    },
    body: JSON.stringify({
      file_hash: fileHash,
      file_name: fileName,
      total_chunks: totalChunks,
      chunk_size: chunkSize,
    }),
  })
  // 检查合并请求响应
  if (!completeRes.ok) {
    const err = await completeRes.json().catch(() => ({}))
    state.status = UploadStatus.FAILED
    state.error = err.error?.message || `complete failed: ${completeRes.status}`
    persist(state)
    throw new Error(state.error)
  }
  // 解析合并任务 jobId
  const completeData = await completeRes.json()
  const jobId = completeData.job_id
  state.jobId = jobId
  persist(state)

  // 5) 轮询后端合并状态，直到成功或失败或超时
  for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
    const statusRes = await fetch(`${backendBaseUrl}/api/upload/status?job_id=${encodeURIComponent(jobId)}`, {
      headers: getAuthHeader() ? { Authorization: getAuthHeader() } : {},
    })
    // 如果请求失败，等待后重试
    if (!statusRes.ok) {
      await sleep(POLL_INTERVAL_MS)
      continue
    }
    // 解析合并状态
    const statusData = await statusRes.json()
    // 合并成功，返回 fileId
    if (statusData.status === 'success' && statusData.file_id) {
      state.status = UploadStatus.SUCCESS
      state.fileId = statusData.file_id
      persist(state)
      return { fileId: statusData.file_id, fileName }
    }
    // 合并失败，抛出错误
    if (statusData.status === 'failed') {
      state.status = UploadStatus.FAILED
      state.error = statusData.error || 'merge failed'
      persist(state)
      throw new Error(state.error)
    }
    // 未完成则等待后继续轮询
    await sleep(POLL_INTERVAL_MS)
  }

  // 超时未完成，标记失败
  state.status = UploadStatus.FAILED
  state.error = 'merge timeout'
  persist(state)
  throw new Error('merge timeout')
}

// 上传单个分片到后端
async function uploadOneChunk(backendBaseUrl, getAuthHeader, fileHash, fileName, totalChunks, chunk) {
  // 构造表单数据
  const form = new FormData()
  form.append('file_hash', fileHash)
  form.append('chunk_index', String(chunk.index))
  form.append('total_chunks', String(totalChunks))
  form.append('file_name', fileName)
  form.append('chunk', chunk.blob)
  // 发送分片上传请求
  const res = await fetch(`${backendBaseUrl}/api/upload/chunk`, {
    method: 'POST',
    headers: getAuthHeader() ? { Authorization: getAuthHeader() } : {},
    body: form,
  })
  // 检查响应
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error?.message || `chunk ${chunk.index} upload failed: ${res.status}`)
  }
  // 返回分片索引
  return chunk.index
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

export { UploadStatus, getTaskState, setTaskState, clearTaskState }
export { listPendingTasks } from './uploadState.js'

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
export async function runUploadTask(file, options) {
  const {
    backendBaseUrl,
    getAuthHeader = () => '',
    chunkSize = DEFAULT_CHUNK_SIZE,
    concurrency = DEFAULT_CONCURRENCY,
    onProgress,
  } = options

  const run = createConcurrencyPool(concurrency)

  // 1) 切片 + 计算文件 hash
  const { fileHash, chunks, totalChunks, fileName, fileSize } = await sliceAndHash(file, { chunkSize })

  const persist = (state) => {
    setTaskState(fileHash, state)
    onProgress?.(state)
  }

  let state = getTaskState(fileHash)
  if (state && (state.status === UploadStatus.SUCCESS && state.fileId)) {
    return { fileId: state.fileId, fileName: state.fileName }
  }
  if (!state) {
    state = {
      status: UploadStatus.WAITING,
      fileHash,
      fileName,
      totalChunks,
      uploadedChunks: [],
      chunkSize,
    }
    persist(state)
  }

  // 2) 问后端：哪些 chunk 已存在
  const checkRes = await fetch(`${backendBaseUrl}/api/upload/check`, {
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
  if (!checkRes.ok) {
    const err = await checkRes.json().catch(() => ({}))
    throw new Error(err.error?.message || `check failed: ${checkRes.status}`)
  }
  const checkData = await checkRes.json()
  if (checkData.exists && checkData.file_id) {
    state = { ...state, status: UploadStatus.SUCCESS, fileId: checkData.file_id, fileName }
    persist(state)
    return { fileId: checkData.file_id, fileName }
  }
  const alreadyUploaded = new Set(checkData.uploaded_chunks || [])

  // 3) 只上传缺失的 chunk（并发池）
  state.status = UploadStatus.UPLOADING
  persist(state)

  const toUpload = chunks.filter((c) => !alreadyUploaded.has(c.index))
  const uploadTask = (chunk) => () =>
    uploadOneChunk(backendBaseUrl, getAuthHeader, fileHash, fileName, totalChunks, chunk).then((index) => {
      state.uploadedChunks = [...(state.uploadedChunks || []), index]
      persist(state)
      return index
    })
  await Promise.all(toUpload.map((chunk) => run(uploadTask(chunk))))

  // 4) 通知后端：上传完成，请合并
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
  if (!completeRes.ok) {
    const err = await completeRes.json().catch(() => ({}))
    state.status = UploadStatus.FAILED
    state.error = err.error?.message || `complete failed: ${completeRes.status}`
    persist(state)
    throw new Error(state.error)
  }
  const completeData = await completeRes.json()
  const jobId = completeData.job_id
  state.jobId = jobId
  persist(state)

  // 5) 轮询合并状态
  for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
    const statusRes = await fetch(`${backendBaseUrl}/api/upload/status?job_id=${encodeURIComponent(jobId)}`, {
      headers: getAuthHeader() ? { Authorization: getAuthHeader() } : {},
    })
    if (!statusRes.ok) {
      await sleep(POLL_INTERVAL_MS)
      continue
    }
    const statusData = await statusRes.json()
    if (statusData.status === 'success' && statusData.file_id) {
      state.status = UploadStatus.SUCCESS
      state.fileId = statusData.file_id
      persist(state)
      return { fileId: statusData.file_id, fileName }
    }
    if (statusData.status === 'failed') {
      state.status = UploadStatus.FAILED
      state.error = statusData.error || 'merge failed'
      persist(state)
      throw new Error(state.error)
    }
    await sleep(POLL_INTERVAL_MS)
  }

  state.status = UploadStatus.FAILED
  state.error = 'merge timeout'
  persist(state)
  throw new Error('merge timeout')
}

async function uploadOneChunk(backendBaseUrl, getAuthHeader, fileHash, fileName, totalChunks, chunk) {
  const form = new FormData()
  form.append('file_hash', fileHash)
  form.append('chunk_index', String(chunk.index))
  form.append('total_chunks', String(totalChunks))
  form.append('file_name', fileName)
  form.append('chunk', chunk.blob)
  const res = await fetch(`${backendBaseUrl}/api/upload/chunk`, {
    method: 'POST',
    headers: getAuthHeader() ? { Authorization: getAuthHeader() } : {},
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error?.message || `chunk ${chunk.index} upload failed: ${res.status}`)
  }
  return chunk.index
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

export { UploadStatus, getTaskState, setTaskState, clearTaskState }
export { listPendingTasks } from './uploadState.js'

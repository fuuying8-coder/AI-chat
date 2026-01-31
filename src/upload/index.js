/**
 * Upload Task 模块入口
 * - 切片 + 内容 hash（slicer）
 * - 并发池（concurrencyPool）
 * - 断点续传 + 状态持久化（uploadState, uploadTask）
 */

export { sliceAndHash, hashBlob, DEFAULT_CHUNK_SIZE } from './slicer.js'
export { createConcurrencyPool, runWithPool } from './concurrencyPool.js'
export {
  UploadStatus,
  getTaskState,
  setTaskState,
  clearTaskState,
  listPendingTasks,
} from './uploadState.js'
export { runUploadTask } from './uploadTask.js'

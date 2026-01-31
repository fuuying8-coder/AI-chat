/**
 * 上传状态管理：waiting / uploading / success / failed
 * 持久化到 localStorage，页面刷新后可恢复
 */

const STORAGE_KEY_PREFIX = 'upload_task_'

export const UploadStatus = {
  WAITING: 'waiting',
  UPLOADING: 'uploading',
  SUCCESS: 'success',
  FAILED: 'failed',
}

/**
 * @param {string} fileHash
 * @returns {string}
 */
function storageKey(fileHash) {
  return `${STORAGE_KEY_PREFIX}${fileHash}`
}

/**
 * 读取任务状态
 * @param {string} fileHash
 * @returns {{ status: string, fileHash?: string, fileName?: string, totalChunks?: number, uploadedChunks?: number[], jobId?: string, fileId?: string, error?: string } | null}
 */
export function getTaskState(fileHash) {
  try {
    const raw = localStorage.getItem(storageKey(fileHash))
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/**
 * 写入任务状态
 * @param {string} fileHash
 * @param {object} state
 */
export function setTaskState(fileHash, state) {
  try {
    localStorage.setItem(storageKey(fileHash), JSON.stringify(state))
  } catch (e) {
    console.warn('upload state persist failed', e)
  }
}

/**
 * 清除任务状态（合并成功或用户取消后可清理）
 * @param {string} fileHash
 */
export function clearTaskState(fileHash) {
  try {
    localStorage.removeItem(storageKey(fileHash))
  } catch {}
}

/**
 * 列出所有未完成的任务（用于恢复）
 * @returns {object[]}
 */
export function listPendingTasks() {
  const list = []
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && key.startsWith(STORAGE_KEY_PREFIX)) {
        const raw = localStorage.getItem(key)
        if (raw) {
          const state = JSON.parse(raw)
          if (state.status === UploadStatus.WAITING || state.status === UploadStatus.UPLOADING) {
            list.push(state)
          }
        }
      }
    }
  } catch {}
  return list
}

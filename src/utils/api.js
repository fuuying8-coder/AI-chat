import { useSettingStore } from '@/stores/setting'

// 使用本地后端服务，如果后端未运行，可以回退到直接调用 API
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3001/api'
const BACKEND_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace('/api', '') || 'http://localhost:3001'
const FALLBACK_API_BASE_URL = 'https://api.siliconflow.com/v1'

// 检查后端连接状态
export const checkBackendConnection = async () => {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/test`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (response.ok) {
      const data = await response.json()
      console.log('✅ 后端服务连接成功:', data)
      return { connected: true, data }
    } else {
      console.warn('⚠️ 后端服务响应异常:', response.status)
      return { connected: false, error: `HTTP ${response.status}` }
    }
  } catch (error) {
    console.warn('❌ 后端服务连接失败:', error.message)
    return { connected: false, error: error.message }
  }
}

// 在模块加载时检查后端连接
if (typeof window !== 'undefined') {
  checkBackendConnection().then((result) => {
    if (result.connected) {
      console.log('🎉 前端已成功连接到后端服务！')
      console.log('📍 后端地址:', BACKEND_BASE_URL)
    } else {
      console.log('⚠️ 后端服务未运行，将使用直接 API 调用模式')
      console.log('💡 提示: 请运行 `cd server && npm run dev` 启动后端服务')
    }
  })
}


import { runUploadTask } from '@/upload/uploadTask'
import { DEFAULT_CHUNK_SIZE } from '@/upload/slicer'

/** 超过此大小走分片上传（任务调度器），否则走单文件上传 */
const CHUNKED_UPLOAD_THRESHOLD = DEFAULT_CHUNK_SIZE

/** 上传文件到百炼，用于 qwen-long 长文档解析，返回 { file_id, filename }。大文件自动走分片+断点续传。 */
export const uploadFileForExtract = async (file, onProgress) => {
  const settingStore = useSettingStore()
  const getAuth = () => `Bearer ${settingStore.settings.apiKeyALi}`

  if (file.size > CHUNKED_UPLOAD_THRESHOLD) {
    const result = await runUploadTask(file, {
      backendBaseUrl: BACKEND_BASE_URL,
      getAuthHeader: getAuth,
      onProgress,
    })
    return { file_id: result.fileId, filename: result.fileName }
  }

  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${BACKEND_BASE_URL}/api/files/upload`, {
    method: 'POST',
    headers: {
      Authorization: getAuth(),
    },
    body: form,
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.error?.message || `上传失败: ${response.status}`)
  }
  return response.json()
}

/**
 * @param {Array} messages
 * @param {{ fileId?: string, stream?: boolean, signal?: AbortSignal }} [extraOptions] - fileId 长文档；stream 流式；signal 用于取消请求
 */
export const createChatCompletion = async (messages, extraOptions = {}) => {
  const settingStore = useSettingStore()
  const useStream = extraOptions.stream ?? settingStore.settings.stream ?? true
  const payload = {
    model: settingStore.settings.model,
    messages,
    stream: useStream,
    max_tokens: settingStore.settings.maxTokens,
    temperature: settingStore.settings.temperature,
    top_p: settingStore.settings.topP,
    top_k: settingStore.settings.topK,
    apiKey: settingStore.settings.apiKey,
  }
  if (extraOptions.fileId != null && String(extraOptions.fileId).trim() !== '') {
    payload.file_id = String(extraOptions.fileId).trim()
  }

  const options_ali = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${settingStore.settings.apiKeyALi}`,
    },
    body: JSON.stringify(payload),
    ...(extraOptions.signal && { signal: extraOptions.signal }),
  }

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/chat/qwen`, options_ali)

    if (!response.ok) {
      const contentType = response.headers.get('content-type') || ''
      if (contentType.includes('application/json')) {
        const errorData = await response.json().catch(() => ({ error: { message: 'Unknown error' } }))
        throw new Error(errorData.error?.message || `HTTP error! status: ${response.status}`)
      }
      const errorText = await response.text().catch(() => 'Unknown error')
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
    }

    if (useStream) {
      return response
    }

    const data = await response.json()
    if (!data.speed && data.usage?.completion_tokens != null) {
      data.speed = Number(data.usage.completion_tokens) || 0
    }
    return data
  } catch (error) {
    console.error('Chat API Error:', error)
    throw error
  }
}

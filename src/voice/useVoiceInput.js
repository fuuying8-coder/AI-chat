/**
 * 语音输入 composable：基于 Web Speech API
 * 功能：麦克风录制控制、语音转写、状态提示（idle/listening/processing/error）
 */

import { ref, computed, onUnmounted } from 'vue'

const SpeechRecognition =
  typeof window !== 'undefined' &&
  (window.SpeechRecognition || window.webkitSpeechRecognition)

export const VoiceStatus = {
  IDLE: 'idle',
  LISTENING: 'listening',
  PROCESSING: 'processing',
  ERROR: 'error',
}

const STATUS_LABELS = {
  [VoiceStatus.IDLE]: '',
  [VoiceStatus.LISTENING]: '正在聆听...',
  [VoiceStatus.PROCESSING]: '识别中...',
  [VoiceStatus.ERROR]: '识别失败',
}

const ERROR_MESSAGES = {
  'not-allowed': '请允许麦克风权限',
  'no-speech': '未检测到语音，请重试',
  'audio-capture': '无法访问麦克风',
  'network': '网络错误，请检查连接',
  'aborted': '已取消',
  'language-not-supported': '当前浏览器不支持该语言',
  default: '语音识别失败，请重试',
}

/**
 * @param {Object} options
 * @param {string} [options.lang='zh-CN'] 识别语言
 * @param {boolean} [options.continuous=true] 是否连续识别
 * @param {boolean} [options.interimResults=true] 是否返回临时结果
 * @param {number} [options.maxAlternatives=1] 最大备选结果数
 */
export function useVoiceInput(options = {}) {
  const {
    lang = 'zh-CN',
    continuous = true,
    interimResults = true,
    maxAlternatives = 1,
  } = options

  const status = ref(VoiceStatus.IDLE)
  const transcript = ref('')
  const interimTranscript = ref('')
  const errorMessage = ref('')

  const isSupported = !!SpeechRecognition
  const isRecording = computed(() => status.value === VoiceStatus.LISTENING)
  const statusLabel = computed(() => STATUS_LABELS[status.value] || '')
  const hasError = computed(() => status.value === VoiceStatus.ERROR)

  let recognition = null

  function getRecognition() {
    if (!SpeechRecognition) return null
    if (!recognition) {
      recognition = new SpeechRecognition()
      recognition.continuous = continuous
      recognition.interimResults = interimResults
      recognition.maxAlternatives = maxAlternatives
      recognition.lang = lang

      recognition.onstart = () => {
        status.value = VoiceStatus.LISTENING
        transcript.value = ''
        interimTranscript.value = ''
        errorMessage.value = ''
      }

      recognition.onresult = (event) => {
        let finalText = ''
        let interimText = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i]
          const text = result[0].transcript
          if (result.isFinal) {
            finalText += text
          } else {
            interimText += text
          }
        }
        if (finalText) transcript.value += finalText
        interimTranscript.value = interimText
      }

      recognition.onend = () => {
        if (status.value === VoiceStatus.LISTENING) {
          status.value = VoiceStatus.PROCESSING
        }
      }

      recognition.onerror = (event) => {
        status.value = VoiceStatus.ERROR
        errorMessage.value = ERROR_MESSAGES[event.error] || ERROR_MESSAGES.default
        if (event.error === 'aborted') {
          status.value = VoiceStatus.IDLE
        }
      }
    }
    return recognition
  }

  function start() {
    if (!isSupported) {
      status.value = VoiceStatus.ERROR
      errorMessage.value = '当前浏览器不支持语音识别，请使用 Chrome 或 Edge'
      return
    }
    const rec = getRecognition()
    if (!rec) return
    try {
      rec.start()
    } catch (e) {
      status.value = VoiceStatus.ERROR
      errorMessage.value = e.message || ERROR_MESSAGES.default
    }
  }

  function stop() {
    if (!recognition || status.value !== VoiceStatus.LISTENING) return
    try {
      recognition.stop()
    } catch (e) {
      // 忽略已停止的情况
    }
    status.value = VoiceStatus.PROCESSING
  }

  function toggle() {
    if (isRecording.value) {
      stop()
    } else {
      start()
    }
  }

  function reset() {
    status.value = VoiceStatus.IDLE
    transcript.value = ''
    interimTranscript.value = ''
    errorMessage.value = ''
  }

  /** 获取最终文本（含临时结果），用于填入输入框 */
  function getFullTranscript() {
    const t = transcript.value + interimTranscript.value
    return t.trim()
  }

  onUnmounted(() => {
    if (recognition && status.value === VoiceStatus.LISTENING) {
      try {
        recognition.abort()
      } catch (e) {}
    }
  })

  return {
    isSupported,
    status,
    transcript,
    interimTranscript,
    errorMessage,
    isRecording,
    statusLabel,
    hasError,
    start,
    stop,
    toggle,
    reset,
    getFullTranscript,
  }
}

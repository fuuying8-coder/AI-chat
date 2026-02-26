/**
 * 语音输入 composable：基于 Web Speech API
 * 功能：麦克风录制控制、语音转写、状态提示（idle/listening/processing/error）
 */

// ref：维护状态与文本；computed：派生是否录音/状态文案/是否错误；onUnmounted：组件卸载时中止识别
import { ref, computed, onUnmounted } from 'vue'

// 获取浏览器语音识别 API：标准为 SpeechRecognition，部分浏览器为 webkitSpeechRecognition
// 服务端渲染时 typeof window === 'undefined'，整段为 false，避免报错
const SpeechRecognition =
  typeof window !== 'undefined' &&
  (window.SpeechRecognition || window.webkitSpeechRecognition)

// 状态枚举：供外部 watch 或模板判断当前处于哪一阶段
export const VoiceStatus = {
  IDLE: 'idle',           // 空闲，未录音
  LISTENING: 'listening', // 正在录音并识别
  PROCESSING: 'processing', // 本次识别刚结束，可取最终文本
  ERROR: 'error',         // 发生错误
}

// 各状态对应的界面提示文案（中文），空字符串表示不显示
const STATUS_LABELS = {
  [VoiceStatus.IDLE]: '',
  [VoiceStatus.LISTENING]: '正在聆听...',
  [VoiceStatus.PROCESSING]: '识别中...',
  [VoiceStatus.ERROR]: '识别失败',
}

// 识别引擎 onerror 时 event.error 的取值 → 用户可读的错误提示；default 为未列出的错误码兜底
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
 * 语音输入 composable
 * @param {Object} options
 * @param {string} [options.lang='zh-CN'] 识别语言
 * @param {boolean} [options.continuous=true] 是否连续识别
 * @param {boolean} [options.interimResults=true] 是否返回临时结果
 * @param {number} [options.maxAlternatives=1] 最大备选结果数
 */
export function useVoiceInput(options = {}) {
  // 解构入参，未传则用默认值
  const {
    lang = 'zh-CN',
    continuous = true,
    interimResults = true,
    maxAlternatives = 1,
  } = options

  // 当前状态（idle / listening / processing / error）
  const status = ref(VoiceStatus.IDLE)
  // 已确认的转写文本（isFinal 为 true 的结果累加）
  const transcript = ref('')
  // 当前临时结果（边说边出的未确认文本）
  const interimTranscript = ref('')
  // 错误时展示的文案
  const errorMessage = ref('')

  // 当前环境是否支持语音识别（有 API 即为 true）
  const isSupported = !!SpeechRecognition
  // 是否正在录音（仅 listening 为 true）
  const isRecording = computed(() => status.value === VoiceStatus.LISTENING)
  // 当前状态对应的中文提示，用于界面展示
  const statusLabel = computed(() => STATUS_LABELS[status.value] || '')
  // 是否处于错误状态，便于模板里区分展示错误文案
  const hasError = computed(() => status.value === VoiceStatus.ERROR)

  // 语音识别实例，懒创建，复用于同一次会话的多次 start/stop
  let recognition = null

  /**
   * 获取或创建 SpeechRecognition 实例，并绑定事件
   * 仅在没有实例时创建，避免重复 new 导致异常
   */
  function getRecognition() {
    if (!SpeechRecognition) return null
    if (!recognition) {
      recognition = new SpeechRecognition()
      recognition.continuous = continuous   // 连续识别，多段话不自动停
      recognition.interimResults = interimResults // 返回临时结果（边说边出）
      recognition.maxAlternatives = maxAlternatives // 每条结果最多备选数
      recognition.lang = lang               // 识别语言，如 zh-CN

      // 开始识别时：进入聆听态，清空上次的转写与错误
      recognition.onstart = () => {
        status.value = VoiceStatus.LISTENING
        transcript.value = ''
        interimTranscript.value = ''
        errorMessage.value = ''
      }

      // 有识别结果时：按 isFinal 区分最终/临时，累加到对应 ref
      // event.results 为 SpeechRecognitionResultList；resultIndex 表示本次事件从第几条开始
      recognition.onresult = (event) => {
        let finalText = ''
        let interimText = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i]
          const text = result[0].transcript  // 取第一条（最佳）转写；maxAlternatives>1 时可有更多备选
          if (result.isFinal) {
            finalText += text  // 已确认的片段，需累加到 transcript
          } else {
            interimText += text  // 临时片段，会随识别更新，只保留当前一段
          }
        }
        if (finalText) transcript.value += finalText  // 追加入已确认文本，不覆盖历史
        interimTranscript.value = interimText        // 临时结果整体替换，下次 onresult 会覆盖
      }

      // 识别结束（用户 stop 或引擎结束）：若还在聆听态则切到处理中，便于取最终文本
      recognition.onend = () => {
        if (status.value === VoiceStatus.LISTENING) {
          status.value = VoiceStatus.PROCESSING
        }
      }

      // 出错：置错误态并设置文案；aborted 视为取消，直接回到空闲
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

  /** 开始录音/识别：不支持则设错误；否则取实例并 start，异常时设错误文案 */
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

  /** 停止录音：仅当实例存在且正在聆听时调用 stop，并置为 processing */
  function stop() {
    if (!recognition || status.value !== VoiceStatus.LISTENING) return
    try {
      recognition.stop()
    } catch (e) {
      // 忽略已停止的情况（如重复 stop）
    }
    status.value = VoiceStatus.PROCESSING
  }

  /** 切换：正在录则 stop，否则 start */
  function toggle() {
    if (isRecording.value) {
      stop()
    } else {
      start()
    }
  }

  /** 重置：回到空闲，清空转写与错误文案，供下次录音前使用 */
  function reset() {
    status.value = VoiceStatus.IDLE
    transcript.value = ''
    interimTranscript.value = ''
    errorMessage.value = ''
  }

  /** 获取本次识别的完整文本（已确认 + 临时），去首尾空格，用于填入输入框 */
  function getFullTranscript() {
    const t = transcript.value + interimTranscript.value
    return t.trim()
  }

  // 组件卸载时若正在录音，中止识别，避免后台继续占用麦克风
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

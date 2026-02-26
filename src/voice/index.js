/**
 * 语音输入子模块入口
 * 基于 Web Speech API：麦克风录制控制、语音转写、状态提示
 */
// 对外只暴露 composable 与状态枚举，便于其他组件 import { useVoiceInput, VoiceStatus } from '@/voice'
export { useVoiceInput, VoiceStatus } from './useVoiceInput.js'

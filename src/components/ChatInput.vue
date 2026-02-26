<script setup>
import { ref, watch } from 'vue'
import { Close, Document, Loading, Microphone } from '@element-plus/icons-vue'
import { useVoiceInput } from '@/voice/useVoiceInput'

// 输入框的值，使用 ref 实现响应式
const inputValue = ref('')

// 语音输入
const voice = useVoiceInput({ lang: 'zh-CN', continuous: true, interimResults: true })
watch(voice.status, (status) => {
  if (status === 'processing') {
    const text = voice.getFullTranscript()
    if (text) {
      inputValue.value = (inputValue.value ? inputValue.value + '\n' : '') + text
    }
    voice.reset()
  }
})
const fileList = ref([]) // 存储上传的文件列表，项含 name, url, type, size, raw, uploadStatus?, fileId?, uploadError?

// 定义组件的 props
const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
  /** 拖拽文件进入时立即执行上传（分片/整文件），回调 setResult(fileId, error) 更新该项状态 */
  onFileDrop: {
    type: Function,
    default: null,
  },
})

const emit = defineEmits(['send', 'stop'])

// 发送：非 loading 时发送；loading 时点击视为停止
const handleSendOrStop = () => {
  if (props.loading) {
    emit('stop')
    return
  }
  if (!inputValue.value.trim()) return
  const messageContent = {
    text: inputValue.value.trim(),
    files: fileList.value,
  }
  emit('send', messageContent)
  inputValue.value = ''
  fileList.value = []
}

// 处理换行的方法（Shift + Enter）
const handleNewline = (e) => {
  e.preventDefault() // 阻止默认的 Enter 发送行为
  inputValue.value += '\n' // 在当前位置添加换行符
}

// 添加一项到文件列表（uploadStatus: idle 表示点击选择，上传在发送时进行；uploading 表示拖拽进入已触发上传）
function addFileToList(file, uploadStatus = 'idle') {
  fileList.value.push({
    name: file.name,
    url: URL.createObjectURL(file),
    type: file.type.startsWith('image/') ? 'image' : 'file',
    size: file.size,
    raw: file,
    uploadStatus, // 'idle' | 'uploading' | 'success' | 'failed'
    fileId: null,
    uploadError: null,
  })
}

// 处理文件上传（点击选择）：仅加入列表，发送时再上传
const handleFileUpload = (uploadFile) => {
  const file = uploadFile.raw
  if (!file) return false
  addFileToList(file, 'idle')
  return false // 阻止自动上传
}

// 拖拽进入：加入列表并立即执行分片/整文件上传
const handleDrop = (e) => {
  e.preventDefault()
  e.stopPropagation()
  isDragOver.value = false
  const files = e.dataTransfer?.files
  if (!files?.length || !props.onFileDrop) return
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (!file) continue
    addFileToList(file, 'uploading')
    const setResult = (fileId, error) => {
      const item = fileList.value.find((x) => x.raw === file)
      if (item) {
        item.fileId = fileId ?? null
        item.uploadStatus = error ? 'failed' : 'success'
        item.uploadError = error?.message ?? null
      }
    }
    props.onFileDrop(file, setResult)
  }
}

const isDragOver = ref(false)
const handleDragOver = (e) => {
  e.preventDefault()
  e.stopPropagation()
  isDragOver.value = true
}
const handleDragLeave = (e) => {
  e.preventDefault()
  e.stopPropagation()
  isDragOver.value = false
}

// 移除文件
const handleFileRemove = (file) => {
  const index = fileList.value.findIndex((item) => item.url === file.url)
  if (index !== -1) {
    URL.revokeObjectURL(fileList.value[index].url)
    fileList.value.splice(index, 1)
  }
}

// 语音输入：生成中禁用；点击切换录音
const handleVoiceToggle = () => {
  if (props.loading) return
  if (!voice.isSupported) {
    return
  }
  voice.toggle()
}
</script>

<template>
  <div
    class="chat-input-wrapper"
    :class="{ 'is-drag-over': isDragOver }"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <!-- 文件预览区域 -->
    <div v-if="fileList.length > 0" class="preview-area">
      <div v-for="file in fileList" :key="file.url" class="preview-item">
        <!-- 图片预览 -->
        <div v-if="file.type === 'image'" class="image-preview">
          <img :src="file.url" :alt="file.name" />
          <div class="remove-btn" @click="handleFileRemove(file)">
            <el-icon><Close /></el-icon>
          </div>
        </div>
        <!-- 文件预览 -->
        <div v-else class="file-preview">
          <el-icon><Document /></el-icon>
          <span class="file-name">{{ file.name }}</span>
          <span class="file-size">{{ (file.size / 1024).toFixed(1) }}KB</span>
          <span v-if="file.uploadStatus === 'uploading'" class="upload-status uploading">上传中…</span>
          <span v-else-if="file.uploadStatus === 'success'" class="upload-status success">已就绪</span>
          <span v-else-if="file.uploadStatus === 'failed'" class="upload-status failed" :title="file.uploadError">失败</span>
          <div class="remove-btn" @click="handleFileRemove(file)">
            <el-icon><Close /></el-icon>
          </div>
        </div>
      </div>
    </div>

    <el-input
      v-model="inputValue"
      type="textarea"
      :autosize="{ minRows: 1, maxRows: 6 }"
      :placeholder="voice.isRecording ? voice.statusLabel : '输入消息，Enter 发送，Shift + Enter 换行'"
      resize="none"
      @keydown.enter.exact.prevent="handleSendOrStop"
      @keydown.enter.shift="handleNewline"
    />
    <!-- 语音状态提示 -->
    <div v-if="voice.statusLabel || voice.errorMessage" class="voice-status">
      <span v-if="voice.hasError" class="voice-error">{{ voice.errorMessage }}</span>
      <span v-else class="voice-hint">{{ voice.statusLabel }}</span>
    </div>
    <div class="button-group">
      <el-upload
        class="upload-btn"
        :auto-upload="false"
        :show-file-list="false"
        :on-change="handleFileUpload"
        accept=".pdf,.doc,.docx,.txt"
      >
        <button class="action-btn">
          <img src="@/assets/photo/附件.png" alt="link" />
        </button>
      </el-upload>
      <el-upload
        class="upload-btn"
        :auto-upload="false"
        :show-file-list="false"
        :on-change="handleFileUpload"
        accept="image/*"
      >
        <button class="action-btn">
          <img src="@/assets/photo/图片.png" alt="picture" />
        </button>
      </el-upload>
      <el-tooltip
        :content="
          !voice.isSupported
            ? '当前浏览器不支持语音输入'
            : voice.isRecording
              ? '点击停止录音'
              : '语音输入'
        "
        placement="top"
      >
        <button
          type="button"
          class="action-btn voice-btn"
          :class="{ 'is-recording': voice.isRecording, 'is-disabled': !voice.isSupported }"
          :disabled="!voice.isSupported || props.loading"
          @click="handleVoiceToggle"
        >
          <el-icon><Microphone /></el-icon>
        </button>
      </el-tooltip>
      <div class="divider"></div>
      <button
        type="button"
        class="action-btn send-btn"
        :class="{ 'is-loading': props.loading }"
        :title="props.loading ? '停止生成' : '发送'"
        @click="handleSendOrStop"
      >
        <template v-if="props.loading">
          <el-icon class="send-loading"><Loading /></el-icon>
          <span class="stop-text">停止</span>
        </template>
        <img v-else src="@/assets/photo/发送.png" alt="send" />
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.chat-input-wrapper {
  padding: 0.8rem;
  background-color: var(--bg-color);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);

  &.is-drag-over {
    border-color: var(--el-color-primary);
    background-color: var(--el-color-primary-light-9, rgba(64, 158, 255, 0.06));
  }

  /* 预览区域容器样式 */
  .preview-area {
    margin-bottom: 8px; /* 与输入框的间距 */
    display: flex; /* 使用弹性布局 */
    flex-wrap: wrap; /* 允许多行显示 */
    gap: 8px; /* 预览项之间的间距 */

    /* 预览项容器样式 */
    .preview-item {
      position: relative; /* 为删除按钮定位做准备 */
      border-radius: 8px; /* 圆角边框 */
      overflow: hidden; /* 隐藏超出部分 */

      /* 图片预览样式 */
      .image-preview {
        width: 60px; /* 固定宽度 */
        height: 60px; /* 固定高度，保持正方形 */

        img {
          width: 100%;
          height: 100%;
          object-fit: cover; /* 保持图片比例并填充容器 */
        }
      }

      /* 文件预览样式 */
      .file-preview {
        padding: 8px; /* 内边距 */
        background-color: #f4f4f5; /* 浅灰色背景 */
        border-radius: 8px; /* 圆角边框 */
        display: flex; /* 使用弹性布局 */
        align-items: center; /* 垂直居中对齐 */
        gap: 8px; /* 元素间距 */

        /* 文件名样式 */
        .file-name {
          max-width: 120px; /* 限制最大宽度 */
          overflow: hidden; /* 隐藏超出部分 */
          text-overflow: ellipsis; /* 超出显示省略号 */
          white-space: nowrap; /* 不换行 */
        }

        /* 文件大小样式 */
        .file-size {
          color: #909399;
          font-size: 12px;
        }

        .upload-status {
          font-size: 11px;
          margin-left: 4px;
          &.uploading {
            color: var(--el-color-primary);
          }
          &.success {
            color: var(--el-color-success);
          }
          &.failed {
            color: var(--el-color-danger);
          }
        }
      }

      /* 删除按钮样式 */
      .remove-btn {
        position: absolute; /* 绝对定位 */
        top: 4px; /* 距顶部距离 */
        right: 4px; /* 距右侧距离 */
        width: 20px; /* 固定宽度 */
        height: 20px; /* 固定高度，保持正圆形 */
        background-color: rgba(0, 0, 0, 0.5); /* 半透明黑色背景 */
        border-radius: 50%; /* 圆形按钮 */
        display: flex; /* 使用弹性布局 */
        align-items: center; /* 垂直居中 */
        justify-content: center; /* 水平居中 */
        cursor: pointer; /* 鼠标指针样式 */
        color: white; /* 图标颜色 */

        /* 鼠标悬停效果 */
        &:hover {
          background-color: rgba(0, 0, 0, 0.7); /* 加深背景色 */
        }
      }
    }
  }

  /* 语音状态提示 */
  .voice-status {
    font-size: 0.75rem;
    color: var(--text-color-secondary);
    min-height: 1rem;
    margin-top: 2px;

    .voice-error {
      color: #e74c3c;
    }
    .voice-hint {
      color: #3f7af1;
    }
  }

  /* 自定义输入框样式 */
  :deep(.el-textarea__inner) {
    border-radius: 8px;
    resize: none;
    border: none;
    box-shadow: none;

    &:focus {
      border: none;
      box-shadow: none;
    }
  }

  /* 按钮组容器样式 */
  .button-group {
    display: flex; /* 使用弹性布局 */
    justify-content: flex-end; /* 按钮靠右对齐 */
    margin-top: 0.25rem; /* 与输入框的上方间距 */
    gap: 0.5rem; /* 按钮之间的间距 */
    align-items: center; /* 垂直居中对齐，让分隔线居中 */

    .upload-btn {
      display: inline-block;
    }

    /* 分隔线样式 */
    .divider {
      height: 1rem; /* 分隔线高度16px */
      width: 1px; /* 分隔线宽度1px */
      background-color: var(--border-color); /* 使用主题变量设置颜色 */
      margin: 0; /* 重置所有边距 */
      margin-left: 0.125rem; /* 左边距2px */
      margin-right: 0.25rem; /* 右边距4px */
    }

    /* 通用按钮样式 */
    .action-btn {
      width: 1.75rem; /* 默认按钮宽度28px */
      height: 1.75rem; /* 默认按钮高度28px */
      border: none; /* 移除边框 */
      background: none; /* 移除背景色 */
      padding: 0; /* 移除内边距 */
      cursor: pointer; /* 鼠标悬停时显示手型 */
      border-radius: 50%; /* 圆形按钮 */
      display: flex; /* 使用弹性布局使图标居中 */
      align-items: center; /* 垂直居中 */
      justify-content: center; /* 水平居中 */
      transition: background-color 0.3s; /* 背景色过渡动画 */

      /* 按钮内图标样式 */
      img {
        width: 1rem; /* 默认图标宽度16px */
        height: 1rem; /* 默认图标高度16px */
      }

      /* 按钮悬停效果 */
      &:hover {
        background-color: rgba(0, 0, 0, 0.05); /* 悬停时显示浅灰色背景 */
      }

      /* 语音按钮 */
      &.voice-btn {
        .el-icon {
          font-size: 1rem;
        }
        &.is-recording {
          background-color: rgba(231, 76, 60, 0.15);
          color: #e74c3c;
          animation: voice-pulse 1.2s ease-in-out infinite;
        }
        &.is-disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }
      }

      /* 发送按钮特殊样式 */
      &.send-btn {
        width: 2rem;
        height: 2rem;
        background-color: #3f7af1;
        gap: 4px;

        img {
          width: 1.25rem;
          height: 1.25rem;
        }

        .send-loading {
          font-size: 1rem;
          animation: spin 0.8s linear infinite;
        }
        .stop-text {
          font-size: 0.75rem;
          color: #fff;
        }

        &:hover {
          background-color: #3266d6;
        }
        &.is-loading {
          cursor: pointer;
          background-color: #e74c3c;
          &:hover {
            background-color: #c0392b;
          }
        }
      }
    }
  }
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@keyframes voice-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
</style>

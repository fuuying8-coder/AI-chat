<script setup lang="ts">
import ChatInput from '@/components/ChatInput.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import { Plus } from '@element-plus/icons-vue'
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { messageHandler } from '@/utils/messageHandler'
import { createChatCompletion, createRagChatCompletion, createCaseStudyChatCompletion, getRagDocuments, uploadFileForExtract, uploadRagDocument } from '@/utils/api'
import { useSettingStore } from '@/stores/setting'
import SettingsPanel from '@/components/SettingsPanel.vue'
import PopupMenu from '@/components/PopupMenu.vue'
import DialogEdit from '@/components/DialogEdit.vue'
import { useRouter } from 'vue-router'

// 获取聊天消息
const chatStore = useChatStore()
const currentMessages = computed(() => chatStore.currentMessages)
const isLoading = computed(() => chatStore.isLoading)
const settingStore = useSettingStore()
let abortController: AbortController | null = null

// RAG 模式：为 true 时走知识库检索 + 生成
const useRagMode = ref(false)
// Case Study 模式：为 true 时走药物 Top-N 关联 miRNA 查询
const useCaseStudyMode = ref(false)
// 知识库上传对话框
const ragUploadVisible = ref(false)
const ragUploadLoading = ref(false)
const ragUploadFile = ref(null)
const ragUploadResult = ref('')
const ragDocumentList = ref<{ filename: string; uploaded_at: string; message: string }[]>([])
const ragDocumentListLoading = ref(false)



onMounted(() => {
  // 每次页面刷新时，将消息容器滚动到底部
   nextTick(() => {
    setTimeout(() => {
      const msgDom = document.getElementById('currentMessages')
      if (msgDom) {
        msgDom.scrollTop = msgDom.scrollHeight
      }
    }, 50)

  })
  // 当没有对话时，默认新建一个对话
  if (chatStore.conversations.length === 0) {
    chatStore.createConversation()
  }
})

// 是否可作为百炼长文档解析（file-extract）
const isExtractableDoc = (name: string) => /\.(docx?|pdf|txt|md)$/i.test(name || '')

// 拖拽文件进入时立即执行分片/整文件上传，回调 setResult(fileId, error) 更新输入框内该项状态
const handleFileDrop = (file: File, setResult: (fileId: string | null, error?: Error) => void) => {
  if (!isExtractableDoc(file.name)) {
    setResult(null) // 非文档类型不走上传，仅加入列表
    return
  }
  uploadFileForExtract(file)
    .then((res) => setResult(res.file_id ?? (res as any).fileId ?? null, undefined))
    .catch((e) => setResult(null, e instanceof Error ? e : new Error(String(e))))
}

// 滚动消息容器到底部（流式生成时随内容滚动）
function scrollToBottom() {
  nextTick(() => {
    const el = document.getElementById('currentMessages')
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 停止生成（取消当前请求）
function handleStop() {
  if (abortController) {
    abortController.abort()
  }
}

type ChatFile = {
  name: string
  url: string
  type: string
  size: number
  raw: File
}

// 发送消息
const handleSend = async (messageContent:{ text: string; files?: ChatFile[] }) => {
  try {
    // 添加用户消息
    chatStore.addMessage(
      messageHandler.formatMessage('user', messageContent.text, '', messageContent.files),
    )
    // 添加空的助手消息（loading: true，先显示「内容生成中」，有内容后显示打字机气泡，生成完后显示四个按钮）
    chatStore.addMessage({ ...messageHandler.formatMessage('assistant', '', ''), loading: true })

    chatStore.setIsLoading(true)
    scrollToBottom()

    const messages = chatStore.currentMessages.map(({ role, content }) => ({ role, content }))
    let fileId = null
    const files = messageContent.files || []
    const docFile = files.find((f) => f.raw && isExtractableDoc(f.name))
    if (docFile) {
      if (docFile.fileId) {
        fileId = docFile.fileId
      } else {
        try {
          const res = await uploadFileForExtract(docFile.raw)
          fileId = res.file_id ?? res.fileId ?? null
          if (!fileId) {
            console.warn('长文档上传成功但未返回 file_id', res)
          }
        } catch (e) {
          console.error('长文档上传失败:', e)
          chatStore.updateLastMessage('长文档上传失败，请重试。')
          chatStore.setIsLoading(false)
          chatStore.setLastMessageLoading(false)
          return
        }
      }
    }

    abortController = new AbortController()
    const useStream = settingStore.settings.stream !== false

    const response = useCaseStudyMode.value
      ? await createCaseStudyChatCompletion(messages, {
          stream: useStream,
          signal: abortController.signal,
        })
      : useRagMode.value
      ? await createRagChatCompletion(messages, {
          stream: useStream,
          signal: abortController.signal,
          sessionId: chatStore.currentConversationId || 'default',
        })
      : await createChatCompletion(messages, {
          fileId: fileId || undefined,
          stream: useStream,
          signal: abortController.signal,
        })

    const isStreamResponse =
      response.body != null && typeof response.body.getReader === 'function'
    await messageHandler.handleResponse(
      response,
      isStreamResponse,
      (
        content: string,
        reasoning_content: string,
        tokens: number,
        speed: number
      ) => {
        chatStore.updateLastMessage(content, reasoning_content, tokens, speed)
        scrollToBottom()
      },
    )
  } catch (error: unknown) {
    const isAbort = error instanceof Error && error.name === 'AbortError'
    if (!isAbort) {
      console.error('Failed to send message:', error)
      chatStore.updateLastMessage('抱歉，发生了一些错误，请稍后重试。')
    }
  } finally {
    abortController = null
    chatStore.setIsLoading(false)
    chatStore.setLastMessageLoading(false)
  }
}

// 重新生成的处理函数
const handleRegenerate = async () => {
  try {
    // 类型保护，确保有足够的消息
    if (chatStore.currentMessages.length < 2) {
      return
    }
    const lastUserMessage = chatStore.currentMessages[chatStore.currentMessages.length - 2] as { content: string; files?: ChatFile[] }
    // 使用 splice 删除最后两个元素
    chatStore.currentMessages.splice(-2, 2)
    await handleSend({ text: lastUserMessage.content, files: lastUserMessage.files })
  } catch (error) {
    console.error('Failed to regenerate message:', error)
  }
}

// 添加抽屉引用
const settingDrawer = ref(null)

// 添加新建对话的处理函数
const handleNewChat = () => {
  chatStore.createConversation()
}

// 获取当前对话标题
const currentTitle = computed(() => chatStore.currentConversation?.title || 'LLM Chat')
// 格式化标题
const formatTitle = (title: string) => {
  return title.length > 4 ? title.slice(0, 4) + '...' : title
}

// 添加对话框组件
const dialogEdit = ref(null)

// 获取路由实例
const router = useRouter()

// 处理返回首页
const handleBack = async () => {
  router.push('/')
}

// 打开知识库上传对话框并拉取已上传文档列表
const openRagUpload = async () => {
  ragUploadResult.value = ''
  ragUploadFile.value = null
  ragUploadVisible.value = true
  ragDocumentListLoading.value = true
  try {
    const res = await getRagDocuments()
    ragDocumentList.value = res.documents || []
  } catch {
    ragDocumentList.value = []
  } finally {
    ragDocumentListLoading.value = false
  }
}

// 提交知识库上传（选文件后上传）
const handleRagUploadSubmit = async () => {
  if (!ragUploadFile.value) {
    return
  }
  ragUploadLoading.value = true
  ragUploadResult.value = ''
  try {
    const res = await uploadRagDocument(ragUploadFile.value)
    ragUploadResult.value = res.message || '[成功]已加入知识库'
    ragDocumentList.value = [
      ...ragDocumentList.value,
      {
        filename: res.filename,
        uploaded_at: new Date().toISOString().slice(0, 19).replace('T', ' '),
        message: res.message,
      },
    ]
  } catch (e) {
    ragUploadResult.value = '上传失败：' + (e.message || String(e))
  } finally {
    ragUploadLoading.value = false
  }
}

// 知识库上传：选择文件
const handleRagFileChange = (uploadFile) => {
  const raw = uploadFile?.raw
  if (raw) ragUploadFile.value = raw
}
</script>

<template>
  <!-- 聊天容器 -->
  <div class="chat-container">
    <!-- 聊天头部 -->
    <div class="chat-header">
      <div class="header-left">
        <PopupMenu ref="popupMenu" />
        <el-button class="new-chat-btn" :icon="Plus" @click="handleNewChat">新对话</el-button>
        <div class="divider"></div>
        <div class="title-wrapper">
          <h1 class="chat-title">{{ formatTitle(currentTitle) }}</h1>
          <button
            class="edit-btn"
            @click="dialogEdit?.openDialog(chatStore.currentConversationId, 'edit')"
          >
            <img src="@/assets/photo/编辑.png" alt="edit" />
          </button>
        </div>
      </div>

      <div class="header-right">
        <el-tooltip content="RAG 知识库问答（开启后将基于已上传文档回答）" placement="top">
          <button
            type="button"
            class="action-btn rag-toggle"
            :class="{ 'is-active': useRagMode }"
            @click="useRagMode = !useRagMode; useCaseStudyMode = false"
          >
            <span class="rag-label">RAG</span>
          </button>
        </el-tooltip>
        <el-tooltip content="药物 Top-N 关联 miRNA 查询（如：查询 Docetaxel 的 top 20 关联 miRNA）" placement="top">
          <button
            type="button"
            class="action-btn rag-toggle"
            :class="{ 'is-active': useCaseStudyMode }"
            @click="useCaseStudyMode = !useCaseStudyMode; useRagMode = false"
          >
            <span class="rag-label">Case</span>
          </button>
        </el-tooltip>
        <el-tooltip content="上传文档到知识库（.txt / .md / .pdf）" placement="top">
          <button type="button" class="action-btn" @click="openRagUpload">
            <span class="rag-label">知识库</span>
          </button>
        </el-tooltip>
        <el-tooltip content="设置" placement="top">
          <button class="action-btn" @click="settingDrawer?.openDrawer()">
            <img src="@/assets/photo/设置.png" alt="settings" />
          </button>
        </el-tooltip>
        <el-tooltip content="回到首页" placement="top">
          <button class="action-btn" @click="handleBack">
            <img src="@/assets/photo/返回.png" alt="back" />
          </button>
        </el-tooltip>
      </div>
    </div>

    <!-- 消息容器，显示对话消息 -->
    <div class="messages-container" id="currentMessages">
      <template v-if="(currentMessages as any[]).length > 0">
        <chat-message
          v-for="(message, index) in currentMessages as any[]"
          :key="(message as any).id"
          :message="message as any"
          :is-last-assistant-message="
            index === (currentMessages as any[]).length - 1 && (message as any).role === 'assistant'
          "
          @regenerate="handleRegenerate"
        />
      </template>
      <div v-else class="empty-state">
        <div class="empty-content">
          <img src="@/assets/photo/对话.png" alt="chat" class="empty-icon" />
          <h2>开始对话吧</h2>
          <p>有什么想和我聊的吗？</p>
        </div>
      </div>
    </div>

    <!-- 聊天输入框（支持拖拽文件进入即分片上传） -->
    <div class="chat-input-container">
      <chat-input
        :loading="isLoading"
        :on-file-drop="handleFileDrop"
        @send="handleSend"
        @stop="handleStop"
      />
    </div>

    <!-- 设置面板 -->
    <SettingsPanel ref="settingDrawer" />

    <!-- 添加对话框组件 -->
    <DialogEdit ref="dialogEdit" />

    <!-- RAG 知识库上传对话框 -->
    <el-dialog
      v-model="ragUploadVisible"
      title="上传到知识库"
      width="440px"
      :close-on-click-modal="true"
    >
      <div class="rag-dialog-body">
        <section class="rag-section">
          <p class="rag-upload-hint">支持 .txt、.md、.pdf 文件，内容将分片向量化并参与 RAG 检索（重复内容按 MD5 去重）。</p>
          <el-upload
            :auto-upload="false"
            :show-file-list="true"
            :on-change="handleRagFileChange"
            accept=".txt,.md,.pdf"
            :limit="1"
          >
            <el-button type="primary">选择文件</el-button>
          </el-upload>
          <div v-if="ragUploadResult" class="rag-upload-result" :class="{ error: ragUploadResult.startsWith('上传失败') }">
            {{ ragUploadResult }}
          </div>
        </section>
        <section class="rag-section">
          <div class="rag-section-title">已有知识库</div>
          <div v-if="ragDocumentListLoading" class="rag-list-loading">加载中…</div>
          <ul v-else-if="ragDocumentList.length" class="rag-doc-list">
            <li v-for="(doc, idx) in ragDocumentList" :key="idx" class="rag-doc-item">
              <span class="rag-doc-name">{{ doc.filename }}</span>
              <span class="rag-doc-time">{{ doc.uploaded_at }}</span>
            </li>
          </ul>
          <div v-else class="rag-list-empty">暂无已上传文档，上传后将在此显示</div>
        </section>
      </div>
      <template #footer>
        <el-button @click="ragUploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="ragUploadLoading" :disabled="!ragUploadFile" @click="handleRagUploadSubmit">
          上传
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style lang="scss" scoped>
/* 定义聊天容器的样式，占据整个视口高度，使用flex布局以支持列方向的布局 */
.chat-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

/* 设置聊天头部的样式，包括对齐方式和背景色等 */
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background-color: var(--bg-color);
  border-bottom: 1px solid #ffffff;

  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;

    .action-btn {
      width: 2rem;
      height: 2rem;
      padding: 0;
      border: none;
      background: none;
      cursor: pointer;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;

      img {
        width: 1.4rem;
        height: 1.4rem;
        opacity: 1;
        transition: filter 0.2s;
      }

      &:hover {
        background-color: rgba(0, 0, 0, 0.05);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
      }
    }

    .new-chat-btn {
      /* 基础尺寸设置 */
      font-size: 0.8rem;
      height: 2rem;
      padding: 0rem 0.5rem;

      /* 文字垂直居中对齐 */
      display: inline-flex; /* 使用 flex 布局 */
      align-items: center; /* 垂直居中对齐 */
      line-height: 1; /* 重置行高 */

      /* 圆角设置 - 添加胶囊形状 */
      border-radius: 9999px; /* 使用较大的值来确保完全的胶囊形状 */

      /* 未选中状态 */
      border: 1px solid #3f7af1;
      background-color: #ffffff;
      color: #3f7af1;

      /* 鼠标悬停效果 */
      &:hover {
        background-color: #3f7af1;
        border-color: #3f7af1;
        color: #ffffff;
      }

      /* 图标样式 */
      :deep(.el-icon) {
        margin-right: 4px;
        font-size: 0.875rem;
      }
    }

    /* 添加分隔线样式 */
    .divider {
      height: 1.5rem; /* 设置分隔线高度 */
      width: 1px; /* 设置分隔线宽度 */
      background-color: #e5e7eb; /* 设置分隔线颜色 */
      margin: 0 0.2rem; /* 设置左右间距 */
    }

    .title-wrapper {
      position: relative;
      display: flex;
      align-items: center;
      gap: 0.5rem;

      .chat-title {
        margin: 0;
        font-size: 0.9rem;
        font-weight: 500;
        color: var(--text-color-primary);
      }

      .edit-btn {
        opacity: 0;
        width: 0.9rem;
        height: 0.9rem;
        padding: 0;
        border: none;
        background: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: opacity 0.2s ease;

        img {
          width: 100%;
          height: 100%;
        }
      }

      &:hover {
        .edit-btn {
          opacity: 1;
        }
      }
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;

    .rag-toggle {
      font-size: 0.75rem;
      padding: 0 0.5rem;
      &.is-active {
        background-color: #3f7af1;
        color: #fff;
        border-radius: 4px;
      }
    }
    .rag-label {
      white-space: nowrap;
    }

    .action-btn {
      width: 2rem;
      height: 2rem;
      padding: 0;
      border: none;
      background: none;
      cursor: pointer;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;

      img {
        width: 1.25rem;
        height: 1.25rem;
        opacity: 1;
        transition: filter 0.2s;
      }

      &:hover {
        background-color: rgba(0, 0, 0, 0.05);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);

        img {
          filter: brightness(0.4);
        }
      }
    }
  }
}

/* 定义消息容器的样式 */
.messages-container {
  flex: 1; /* 占据剩余空间 */
  overflow-y: auto; /* 垂直方向可滚动 */
  padding: 0.6rem; /* 四周内边距 */
  background-color: var(--bg-color-secondary); /* 使用主题变量设置背景色 */

  /* 设置最大宽度和居中对齐，与输入框保持一致 */
  max-width: 796px; /* 设置最大宽度 */
  min-width: 0; /* 设置最小宽度 */
  margin: 0 auto; /* 水平居中 */
  width: 100%; /* 在最大宽度范围内占满宽度 */

  /* 自定义滚动条样式 */
  &::-webkit-scrollbar {
    width: 6px; /* 滚动条宽度 */
  }

  &::-webkit-scrollbar-thumb {
    background-color: #ddd; /* 滚动条滑块颜色 */
    border-radius: 3px; /* 滚动条滑块圆角 */
  }

  &::-webkit-scrollbar-track {
    background-color: transparent; /* 滚动条轨道透明 */
  }
}

/* 设置空状态时的样式，占据全部高度，居中对齐内容 */
.empty-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;

  .empty-content {
    text-align: center;

    .empty-icon {
      width: 64px;
      height: 64px;
      opacity: 0.6;
      margin-bottom: 1.5rem;
    }

    h2 {
      font-size: 1.5rem;
      font-weight: 500;
      color: var(--text-color-primary);
      margin-bottom: 0.5rem;
    }

    p {
      font-size: 1rem;
      color: var(--text-color-secondary);
      margin: 0;
    }
  }
}

/* 添加输入框容器样式 */
.chat-input-container {
  position: sticky; /* 使用粘性定位，当滚动到底部时固定位置 */
  bottom: 0; /* 固定在底部 */
  left: 0; /* 左边缘对齐 */
  right: 0; /* 右边缘对齐 */
  background-color: var(--bg-color); /* 使用主题变量设置背景色 */
  z-index: 10; /* 设置层级，确保输入框始终显示在其他内容之上 */
  padding: 0.6rem; /* 添加内边距，让输入框与边缘保持距离 */
  // padding-top: 0; /* 移除顶部内边距，只保留底部和左右的间距 */

  /* 添加最大宽度和居中对齐 */
  max-width: 796px; /* 设置最大宽度 */
  margin: 0 auto; /* 水平居中 */
  width: 100%; /* 在最大宽度范围内占满宽度 */
}

.rag-dialog-body {
  .rag-section {
    margin-bottom: 1rem;
    &:last-of-type {
      margin-bottom: 0;
    }
  }
  .rag-section-title {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-color-primary);
    margin-bottom: 0.5rem;
  }
  .rag-upload-hint {
    font-size: 0.85rem;
    color: var(--text-color-secondary);
    margin-bottom: 0.75rem;
  }
  .rag-upload-result {
    margin-top: 0.5rem;
    font-size: 0.9rem;
    color: #67c23a;
    &.error {
      color: #f56c6c;
    }
  }
  .rag-list-loading,
  .rag-list-empty {
    font-size: 0.85rem;
    color: var(--text-color-secondary);
    padding: 0.5rem 0;
  }
  .rag-doc-list {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 0.25rem 0;
  }
  .rag-doc-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0.75rem;
    font-size: 0.85rem;
    border-bottom: 1px solid var(--border-color);
    &:last-child {
      border-bottom: none;
    }
  }
  .rag-doc-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-right: 0.5rem;
  }
  .rag-doc-time {
    color: var(--text-color-secondary);
    font-size: 0.8rem;
    flex-shrink: 0;
  }
}
</style>

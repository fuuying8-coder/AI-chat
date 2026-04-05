import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import { chatDb } from '@/utils/chatDb'

export const useChatStore = defineStore(
  'llm-chat',
  () => {
    // 所有对话列表（仅保存元信息；消息历史存 IndexedDB）
    const conversations = ref([
      {
        id: '1',
        title: '日常问候',
        createdAt: Date.now(),
      },
    ])

    // conversationId -> messages[]（内存缓存，刷新后从 IndexedDB 恢复）
    const messagesByConversationId = ref({})
    const _loadedConversationIds = new Set()

    const _getOrInitMessages = (conversationId) => {
      if (!conversationId) return []
      if (!messagesByConversationId.value[conversationId]) {
        messagesByConversationId.value[conversationId] = []
      }
      return messagesByConversationId.value[conversationId]
    }

    const ensureMessagesLoaded = async (conversationId) => {
      if (!conversationId) return
      if (_loadedConversationIds.has(conversationId)) return
      const existing = Array.isArray(messagesByConversationId.value[conversationId])
        ? messagesByConversationId.value[conversationId]
        : []
      const loaded = await chatDb.getMessages(conversationId)
      const loadedList = Array.isArray(loaded) ? loaded : []

      // Merge by message.id to avoid overwriting newly added messages
      const byId = new Map()
      for (const m of loadedList) {
        if (m && m.id != null) byId.set(m.id, m)
      }
      for (const m of existing) {
        if (m && m.id != null) byId.set(m.id, m)
      }
      const merged = Array.from(byId.values()).sort((a, b) => {
        const ta = a.timestamp ? Date.parse(a.timestamp) : NaN
        const tb = b.timestamp ? Date.parse(b.timestamp) : NaN
        if (!Number.isNaN(ta) && !Number.isNaN(tb) && ta !== tb) return ta - tb
        return Number(a.id) - Number(b.id)
      })

      messagesByConversationId.value[conversationId] = merged
      _loadedConversationIds.add(conversationId)
    }

    // 当前选中的对话 ID
    const currentConversationId = ref('1')

    // 加载状态
    const isLoading = ref(false)

    // 获取当前对话
    const currentConversation = computed(() => {
      return conversations.value.find((conv) => conv.id === currentConversationId.value)
    })

    // 获取当前对话的消息（从内存缓存读取；必要时自动初始化为空数组）
    const currentMessages = computed(() => {
      return _getOrInitMessages(currentConversationId.value)
    })

    // 创建新对话
    const createConversation = () => {
      const newConversation = {
        id: Date.now().toString(),
        title: '日常问候',
        createdAt: Date.now(),
      }
      conversations.value.unshift(newConversation)
      currentConversationId.value = newConversation.id
      _getOrInitMessages(newConversation.id)
      _loadedConversationIds.add(newConversation.id)
    }

    // 切换对话
    const switchConversation = (conversationId) => {
      currentConversationId.value = conversationId
      ensureMessagesLoaded(conversationId)
    }

    const _normalizeMessageForStorage = (message) => {
      if (!message || typeof message !== 'object') return message
      const stored = { ...message }
      if (Array.isArray(stored.files)) {
        stored.files = stored.files.map((f) => {
          if (!f || typeof f !== 'object') return f
          const { raw, ...rest } = f
          return rest
        })
      }
      if (stored.loading != null) stored.loading = false
      return stored
    }

    // 添加消息到当前对话（写入内存；IndexedDB 异步落盘）
    const addMessage = (message) => {
      const convId = currentConversationId.value
      if (!convId) return
      void ensureMessagesLoaded(convId)
      const list = _getOrInitMessages(convId)
      const msg = {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        ...message,
      }
      list.push(msg)
      void chatDb.putMessage(convId, _normalizeMessageForStorage(msg))
    }

    const setIsLoading = (value) => {
      isLoading.value = value
    }

    // 流式更新会很频繁：对 IndexedDB 写入做节流，避免卡顿。
    let _pendingLastSaveTimer = null
    const _schedulePersistLastMessage = (convId, message, flush = false) => {
      if (!convId || !message) return
      if (_pendingLastSaveTimer) {
        clearTimeout(_pendingLastSaveTimer)
        _pendingLastSaveTimer = null
      }
      const doSave = async () => {
        try {
          await chatDb.putMessage(convId, _normalizeMessageForStorage(message))
        } catch (e) {
          console.warn('Failed to persist last message to IndexedDB:', e)
        }
      }
      if (flush) {
        void doSave()
        return
      }
      _pendingLastSaveTimer = setTimeout(() => {
        _pendingLastSaveTimer = null
        void doSave()
      }, 500)
    }

    const updateLastMessage = (content, reasoning_content, completion_tokens, speed) => {
      const convId = currentConversationId.value
      const list = _getOrInitMessages(convId)
      if (list.length > 0) {
        const lastMessage = list[list.length - 1]
        lastMessage.content = content
        lastMessage.reasoning_content = reasoning_content
        lastMessage.completion_tokens = completion_tokens
        lastMessage.speed = speed
        _schedulePersistLastMessage(convId, lastMessage, false)
      }
    }

    /** 设置最后一条消息的 loading（生成结束后设为 false，用于隐藏「内容生成中」并显示底部四个按钮） */
    const setLastMessageLoading = (value) => {
      const convId = currentConversationId.value
      const list = _getOrInitMessages(convId)
      if (list.length > 0) {
        const lastMessage = list[list.length - 1]
        lastMessage.loading = value
        // 生成结束时强制落盘一次，确保最终内容写入。
        _schedulePersistLastMessage(convId, lastMessage, value === false)
      }
    }

    const getLastMessage = () => {
      const convId = currentConversationId.value
      const list = _getOrInitMessages(convId)
      if (list.length > 0) return list[list.length - 1]
      return null
    }

    const removeLastMessages = async (count = 1) => {
      const convId = currentConversationId.value
      await ensureMessagesLoaded(convId)
      const list = _getOrInitMessages(convId)
      const removed = list.splice(-count, count)
      for (const m of removed) {
        if (m && m.id != null) {
          try {
            await chatDb.deleteMessage(convId, m.id)
          } catch (e) {
            console.warn('Failed to delete message from IndexedDB:', e)
          }
        }
      }
      return removed
    }

    // 更新对话标题
    const updateConversationTitle = (conversationId, newTitle) => {
      const conversation = conversations.value.find((c) => c.id === conversationId)
      if (conversation) {
        conversation.title = newTitle
      }
    }

    // 删除对话
    const deleteConversation = (conversationId) => {
      const index = conversations.value.findIndex((c) => c.id === conversationId)
      if (index !== -1) {
        conversations.value.splice(index, 1)

        // 删除 IndexedDB 中该会话的消息
        void chatDb.deleteConversationMessages(conversationId).catch((e) => {
          console.warn('Failed to delete conversation messages from IndexedDB:', e)
        })
        delete messagesByConversationId.value[conversationId]
        _loadedConversationIds.delete(conversationId)

        // 如果删除后没有对话了，创建一个新对话
        if (conversations.value.length === 0) {
          createConversation()
        }
        // 如果删除的是当前对话，切换到第一个对话
        else if (conversationId === currentConversationId.value) {
          currentConversationId.value = conversations.value[0].id
          ensureMessagesLoaded(currentConversationId.value)
        }
      }
    }

    // 迁移：旧版本把 messages 放在 conversations 里并持久化到 LocalStorage。
    // 新版本把 messages 写入 IndexedDB 并从 conversations 中移除。
    const migrateLegacyLocalStorageState = async () => {
      const legacyConvs = conversations.value
      const hasLegacyMessages = Array.isArray(legacyConvs) && legacyConvs.some((c) => Array.isArray(c?.messages) && c.messages.length)
      if (!hasLegacyMessages) return

      for (const c of legacyConvs) {
        if (!c || !c.id) continue
        const legacyMessages = Array.isArray(c.messages) ? c.messages : []
        if (legacyMessages.length) {
          try {
            await chatDb.putMessages(c.id, legacyMessages)
          } catch (e) {
            console.warn('Failed to migrate messages to IndexedDB:', e)
          }
        }
      }

      // Strip messages from in-memory conversations
      conversations.value = legacyConvs.map((c) => {
        if (!c) return c
        const { messages, ...meta } = c
        return meta
      })
    }

    // 自动加载当前会话消息
    watch(
      currentConversationId,
      (id) => {
        void ensureMessagesLoaded(id)
      },
      { immediate: true },
    )

    return {
      conversations,
      currentConversationId,
      currentConversation,
      currentMessages,
      isLoading,
      addMessage,
      setIsLoading,
      updateLastMessage,
      setLastMessageLoading,
      getLastMessage,
      removeLastMessages,
      ensureMessagesLoaded,
      migrateLegacyLocalStorageState,
      createConversation,
      switchConversation,
      updateConversationTitle,
      deleteConversation,
    }
  },
  {
    // 仅持久化会话元信息和当前选中会话；消息历史进入 IndexedDB。
    persist: {
      paths: ['conversations', 'currentConversationId'],
      async afterRestore(ctx) {
        // afterRestore 在 hydration 后调用：可安全读取到旧的 conversations.messages 并迁移。
        try {
          await ctx.store.migrateLegacyLocalStorageState()
          await ctx.store.ensureMessagesLoaded(ctx.store.currentConversationId)
        } catch (e) {
          console.warn('Chat store afterRestore migration/load failed:', e)
        }
      },
    },
  },
)

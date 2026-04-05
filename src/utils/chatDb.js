import { openDB } from 'idb'

const DB_NAME = 'llm-chat'
const DB_VERSION = 1

const STORE_MESSAGES = 'messages'

/**
 * Message schema stored in IndexedDB:
 * - key: [conversationId, id]
 * - value: { conversationId, id, role, content, reasoning_content, files?, timestamp?, completion_tokens?, speed? }
 */
async function getDb() {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_MESSAGES)) {
        const store = db.createObjectStore(STORE_MESSAGES, {
          keyPath: ['conversationId', 'id'],
        })
        store.createIndex('conversationId', 'conversationId')
        store.createIndex('timestamp', 'timestamp')
      }
    },
  })
}

function normalizeFilesForStorage(files) {
  if (!Array.isArray(files) || files.length === 0) return []
  return files.map((f) => {
    if (!f || typeof f !== 'object') return f
    const { raw, ...rest } = f
    return rest
  })
}

function normalizeMessageForStorage(message) {
  if (!message || typeof message !== 'object') return message
  const stored = { ...message }

  if (stored.files) {
    stored.files = normalizeFilesForStorage(stored.files)
  }

  // UI-only fields should not survive reloads
  if (stored.loading != null) stored.loading = false

  return stored
}

export const chatDb = {
  async getMessages(conversationId) {
    const db = await getDb()
    const tx = db.transaction(STORE_MESSAGES, 'readonly')
    const index = tx.store.index('conversationId')
    const rows = await index.getAll(conversationId)
    await tx.done

    // Stable order (timestamp preferred, fallback to id)
    return (rows || [])
      .map((r) => ({ ...r, loading: false }))
      .sort((a, b) => {
        const ta = a.timestamp ? Date.parse(a.timestamp) : NaN
        const tb = b.timestamp ? Date.parse(b.timestamp) : NaN
        if (!Number.isNaN(ta) && !Number.isNaN(tb) && ta !== tb) return ta - tb
        return Number(a.id) - Number(b.id)
      })
  },

  async putMessage(conversationId, message) {
    const db = await getDb()
    const stored = normalizeMessageForStorage(message)
    await db.put(STORE_MESSAGES, {
      conversationId,
      ...stored,
    })
  },

  async putMessages(conversationId, messages) {
    const db = await getDb()
    const tx = db.transaction(STORE_MESSAGES, 'readwrite')
    for (const message of messages || []) {
      const stored = normalizeMessageForStorage(message)
      await tx.store.put({ conversationId, ...stored })
    }
    await tx.done
  },

  async deleteMessage(conversationId, messageId) {
    const db = await getDb()
    await db.delete(STORE_MESSAGES, [conversationId, messageId])
  },

  async deleteConversationMessages(conversationId) {
    const db = await getDb()
    const tx = db.transaction(STORE_MESSAGES, 'readwrite')
    const index = tx.store.index('conversationId')

    let cursor = await index.openCursor(conversationId)
    while (cursor) {
      await cursor.delete()
      cursor = await cursor.continue()
    }

    await tx.done
  },
}

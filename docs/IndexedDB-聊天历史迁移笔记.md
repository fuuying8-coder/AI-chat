# IndexedDB 聊天历史迁移笔记（LLM Chat Box 2.0）

日期：2026-03-04

## 背景：为什么要迁移

项目原先使用 `pinia-plugin-persistedstate` 将 `chat` store 整体持久化到 LocalStorage。
由于 store 内包含 `conversations[].messages` 全量聊天历史，随着多会话/多轮对话增长，会带来：

- LocalStorage 容量上限较小（常见约 5–10MB），历史一多容易写满导致持久化失败。
- LocalStorage 读写是同步的，流式更新（频繁 `updateLastMessage`）会导致序列化/写入频繁，可能卡 UI。
- 消息里可能包含 `files[].raw: File` 等大对象，不适合落到 LocalStorage。

因此将「消息历史」迁移到 IndexedDB，仅在 LocalStorage 中保留「会话元信息」。

## 目标与策略

- LocalStorage（Pinia persist）只存：
  - `conversations`（仅 `id/title/createdAt`）
  - `currentConversationId`
- IndexedDB 存：
  - 每条 message（按 `conversationId` 分组）

设计原则：
- **不改变现有 UI/UX**：聊天页面、会话切换、编辑/删除对话的交互保持一致。
- **降低写入频率**：流式输出时对 IndexedDB 落盘做节流（避免每个 SSE chunk 都写一次）。
- **自动迁移**：检测到旧版本持久化数据中存在 `conversations[].messages` 时，首次运行自动导入 IndexedDB，然后剥离 `messages` 字段。

## 代码位置

- IndexedDB 访问封装：
  - `src/utils/chatDb.js`
- Pinia store 改造：
  - `src/stores/chat.js`
- 重新生成（Regenerate）逻辑同步删除 IDB：
  - `src/views/ChatView.vue`

## IndexedDB 数据模型

DB：`llm-chat`（version=1）

ObjectStore：`messages`
- 主键（keyPath）：`[conversationId, id]`
- Index：
  - `conversationId`：按会话查询所有 messages
  - `timestamp`：备用索引（当前主要靠 conversationId 拉取后排序）

注意：为降低存储体积与避免结构化克隆问题，写入时会：
- 删除 `files[].raw`（仅保留可展示的元信息，如 name/url/type/size/fileId 等）
- 强制 `loading=false`（UI 临时状态不跨刷新）

## Store 改造要点

### 1) conversations 只保存元信息

`conversations` 结构从：

```js
{ id, title, messages: [], createdAt }
```

变为：

```js
{ id, title, createdAt }
```

消息缓存改为：

- `messagesByConversationId[conversationId] = message[]`

### 2) 切换会话时按需加载

- `switchConversation(id)` 会触发 `ensureMessagesLoaded(id)`
- store 内还有一个 `watch(currentConversationId, ...)`，首次启动会自动加载当前会话消息

### 3) 流式更新写入节流

- `updateLastMessage(...)` 仍然更新内存态用于 UI 逐字渲染
- IndexedDB 写入通过 `setTimeout(500ms)` 合并（最后一条消息持续更新时不会每次都落盘）
- 生成结束时 `setLastMessageLoading(false)` 会触发一次 `flush`，保证最终内容写入

### 4) Regenerate 删除逻辑

由于消息已进入 IndexedDB，不能再直接对 `chatStore.currentMessages.splice()` 做删除（会造成 IDB 残留）。

改为调用 store action：

- `removeLastMessages(2)`：删除最后两条（user + assistant）并同步删 IndexedDB

## 迁移逻辑（Legacy → IndexedDB）

迁移触发点：`persist.afterRestore`（hydration 完成后）。

迁移条件：
- `conversations` 中存在旧字段 `messages` 且不为空。

迁移流程：
1. 遍历旧 conversations，将每个 `conversation.messages` 批量 `put` 到 IndexedDB。
2. 将 `conversations` 原地改写为仅保留元信息（剥离 messages）。
3. 之后 persist 会把新结构写回 LocalStorage，从而避免重复迁移。

## 已知限制与后续建议

- 当前 IndexedDB 只存前端侧“展示所需”的消息字段；如要做文件的离线复现，需要额外设计文件缓存（通常不建议）。
- 如果未来消息量非常大，建议加：
  - 每会话最大消息数/最大字符数裁剪
  - 分页加载（不要一次 getAll 整个会话）
  - 或把历史下沉到后端（实现多端同步）

## 本次依赖变更

新增依赖：
- `idb`（用于简化 IndexedDB API）

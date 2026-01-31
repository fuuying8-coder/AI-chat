/**
 * 文件切片 + 内容哈希（chunk hash + 文件唯一 hash）
 * 固定大小切片，每个 chunk 计算 SHA-256，文件 hash = hash(concat(chunk_hashes))
 */

const DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024 // 2MB

/**
 * 计算 Blob 的 SHA-256 hex
 * @param {Blob} blob
 * @returns {Promise<string>}
 */
export async function hashBlob(blob) {
  const buf = await blob.arrayBuffer()
  const hashBuffer = await crypto.subtle.digest('SHA-256', buf)
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

/**
 * 将文件切成固定大小块，并计算每个 chunk 的 hash
 * @param {File} file
 * @param {{ chunkSize?: number }} options
 * @returns {Promise<{ fileHash: string, chunks: { index: number, blob: Blob, hash: string }[], totalChunks: number, fileName: string, fileSize: number }>}
 */
export async function sliceAndHash(file, options = {}) {
  const chunkSize = options.chunkSize ?? DEFAULT_CHUNK_SIZE
  const totalChunks = Math.ceil(file.size / chunkSize)
  const chunks = []

  for (let i = 0; i < totalChunks; i++) {
    const start = i * chunkSize
    const end = Math.min(start + chunkSize, file.size)
    const blob = file.slice(start, end)
    const hash = await hashBlob(blob)
    chunks.push({ index: i, blob, hash })
  }

  // 文件唯一 hash：对所有 chunk hash 拼接后再 hash，避免重复上传同一文件
  const concatHashes = chunks.map((c) => c.hash).join('')
  const concatBuf = new TextEncoder().encode(concatHashes)
  const fileHashBuffer = await crypto.subtle.digest('SHA-256', concatBuf)
  const fileHash = Array.from(new Uint8Array(fileHashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')

  return {
    fileHash,
    chunks,
    totalChunks,
    fileName: file.name,
    fileSize: file.size,
    chunkSize,
  }
}

export { DEFAULT_CHUNK_SIZE }

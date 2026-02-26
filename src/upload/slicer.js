
/**
 * 文件切片与内容哈希工具：
 * 1. 将文件按固定大小切片
 * 2. 计算每个分片的 SHA-256 哈希
 * 3. 拼接所有分片哈希后再整体哈希，得到文件唯一 hash
 * 用于大文件分片上传、断点续传、去重等场景
 */

// 默认分片大小为 2MB
const DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024 // 2MB


/**
 * 计算 Blob（二进制数据）的 SHA-256 哈希值（16进制字符串）
 * @param {Blob} blob - 要计算哈希的二进制数据
 * @returns {Promise<string>} - 返回哈希字符串
 */
export async function hashBlob(blob) {
  // 将 Blob 转为 ArrayBuffer
  const buf = await blob.arrayBuffer()
  // 计算 SHA-256 哈希，返回 ArrayBuffer
  const hashBuffer = await crypto.subtle.digest('SHA-256', buf)
  // 转为字节数组并格式化为 16 进制字符串
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}


/**
 * 将文件切片并计算每个分片的哈希，同时生成文件唯一 hash
 * @param {File} file - 需要切片的文件对象
 * @param {{ chunkSize?: number }} options - 可选，分片大小
 * @returns {Promise<{ fileHash: string, chunks: { index: number, blob: Blob, hash: string }[], totalChunks: number, fileName: string, fileSize: number, chunkSize: number }>}
 */
export async function sliceAndHash(file, options = {}) {
  const chunkSize = options.chunkSize ?? DEFAULT_CHUNK_SIZE
  const totalChunks = Math.ceil(file.size / chunkSize)
  // 存储所有分片信息
  const chunks = []

  // 遍历每个分片，切片并计算 hash
  for (let i = 0; i < totalChunks; i++) {
    const start = i * chunkSize // 分片起始字节
    const end = Math.min(start + chunkSize, file.size) // 分片结束字节
    const blob = file.slice(start, end) // 切片
    const hash = await hashBlob(blob) // 计算分片 hash
    chunks.push({ index: i, blob, hash }) // 保存分片信息
  }

  // 文件唯一 hash：将所有分片 hash 拼接后整体再 hash，防止同名不同内容文件冲突
  const concatHashes = chunks.map((c) => c.hash).join('') // 拼接所有分片 hash
  const concatBuf = new TextEncoder().encode(concatHashes) // 转为字节流
  const fileHashBuffer = await crypto.subtle.digest('SHA-256', concatBuf) // 计算整体 hash
  const fileHash = Array.from(new Uint8Array(fileHashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')

  // 返回切片和 hash 结果
  return {
    fileHash, // 文件唯一 hash
    chunks, // 分片数组
    totalChunks, // 分片总数
    fileName: file.name, // 文件名
    fileSize: file.size, // 文件大小
    chunkSize, // 分片大小
  }
}

export { DEFAULT_CHUNK_SIZE }

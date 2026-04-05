export const messageHandler = {
  formatMessage(role, content, reasoning_content = '', files = []) {
    return {
      id: Date.now(),
      role,
      content,
      reasoning_content,
      files,
      completion_tokens: 0,
      speed: 0,
      loading: false,
    }
  },

  _sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms))
  },

  _computeBackoffMs(attempt, baseDelayMs, maxDelayMs, jitterRatio) {
    const exp = Math.min(maxDelayMs, baseDelayMs * Math.pow(2, Math.max(0, attempt - 1)))
    const jitter = exp * (jitterRatio || 0)
    const delta = jitter ? (Math.random() * jitter * 2 - jitter) : 0
    return Math.max(0, Math.round(exp + delta))
  },

  _isAbortError(err) {
    return err && (err.name === 'AbortError' || String(err.message || '').includes('aborted'))
  },

  _isRetryableStreamError(err) {
    if (!err) return false
    if (this._isAbortError(err)) return false
    // fetch/stream interrupted errors vary by browser; keep this permissive
    const msg = String(err.message || err)
    return (
      err instanceof TypeError ||
      /network|failed to fetch|fetch|stream|connection|socket|terminated|reset/i.test(msg)
    )
  },

  _normalizeMessagesForRequest(messages) {
    const arr = Array.isArray(messages) ? messages.slice() : []
    // Drop a trailing empty assistant placeholder (common in this app)
    const last = arr[arr.length - 1]
    if (last && last.role === 'assistant' && (!last.content || String(last.content).trim() === '')) {
      arr.pop()
    }
    return arr
  },

  _buildResumeMessages(baseMessages, resumeContent, resumeReasoning, resumeTailChars = 200) {
    const normalized = this._normalizeMessagesForRequest(baseMessages)
    const safeContent = String(resumeContent || '')
    const tail = safeContent.slice(Math.max(0, safeContent.length - resumeTailChars))
    const resumeUser =
      '刚才流式输出中断了。请从「已输出内容」的末尾继续续写，不要重复已输出内容。' +
      '\n若你即将重复，请以“末尾片段”为对齐基准，从其后继续输出。' +
      `\n\n【已输出内容（截至中断）】\n${safeContent}` +
      `\n\n【末尾片段（对齐用）】\n${tail}`

    // Put the partial assistant message into history, then ask to continue.
    return [
      ...normalized,
      { role: 'assistant', content: safeContent, ...(resumeReasoning ? { reasoning_content: resumeReasoning } : {}) },
      { role: 'user', content: resumeUser },
    ]
  },

  // 处理流式响应
  async handleStreamResponse(response, updateCallback) {
    const reader = response.body.getReader() // 获取流 reader
    const decoder = new TextDecoder()  // 把二进制解码成字符串
    let accumulatedContent = ''   // 缓存不完整的行
    let accumulatedReasoning = ''
    let startTime = Date.now()
    let buffer = '' // 用于存储不完整的数据块
    let hasError = false
    let errorMessage = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          // // 处理剩余的缓冲区数据
          // if (buffer.trim()) {
          //   const trimmedLine = buffer.trim()
          //   if (trimmedLine && trimmedLine.startsWith('data: ') && trimmedLine !== 'data: [DONE]') {
          //     try {
          //       const jsonStr = trimmedLine.slice(6)
          //       if (jsonStr && jsonStr.trim() !== '') {
          //         const data = JSON.parse(jsonStr)
          //         if (data.choices?.[0]?.delta) {
          //           const content = data.choices[0].delta.content || ''
          //           const reasoning = data.choices[0].delta.reasoning_content || ''
          //           accumulatedContent += content
          //           accumulatedReasoning += reasoning
          //           updateCallback(
          //             accumulatedContent,
          //             accumulatedReasoning,
          //             data.usage?.completion_tokens || 0,
          //             ((data.usage?.completion_tokens || 0) / ((Date.now() - startTime) / 1000)).toFixed(2),
          //           )
          //         }
          //       }
          //     } catch (parseError) {
          //       console.warn('Failed to parse final buffer:', trimmedLine, parseError)
          //     }
          //   }
          // }
          break
        }

        // 把新 chunk 转成字符串并追加到 buffer
        buffer += decoder.decode(value, { stream: true })

        // 按行分割，保留最后一行（可能不完整）
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // 保留最后一行作为缓冲区

        // 处理完整的行
        for (const line of lines) {
          const trimmedLine = line.trim()
          if (!trimmedLine) continue

          if (trimmedLine === 'data: [DONE]') continue

          if (trimmedLine.startsWith('data: ')) {
            try {
              const jsonStr = trimmedLine.slice(6) // 'data: ' 是 6 个字符
              if (!jsonStr || jsonStr.trim() === '') continue

              const data = JSON.parse(jsonStr)

              // 检查是否有错误
              if (data.error) {
                hasError = true
                errorMessage = data.error.message || JSON.stringify(data.error)
                console.error('Stream error:', data.error)
                break
              }

              // 更新累积内容
              if (data.choices?.[0]?.delta) {
                const content = data.choices[0].delta.content || ''
                const reasoning = data.choices[0].delta.reasoning_content || ''

                accumulatedContent += content
                accumulatedReasoning += reasoning

                // 通过回调更新消息
                updateCallback(
                  accumulatedContent,
                  accumulatedReasoning,
                  data.usage?.completion_tokens || 0,
                  ((data.usage?.completion_tokens || 0) / ((Date.now() - startTime) / 1000)).toFixed(2),
                )
              }
            } catch (parseError) {
              // 忽略 JSON 解析错误，可能是数据不完整
              console.warn('Failed to parse stream line:', trimmedLine, parseError)
            }
          }
        }

        // 如果检测到错误，提前退出
        if (hasError) {
          break
        }
      }

      // 如果检测到错误，抛出异常
      if (hasError) {
        throw new Error(errorMessage || 'Stream processing error')
      }
    } catch (error) {
      console.error('Stream processing error:', error)
      throw error
    }
  },

  /**
   * 断线重连版流式处理：
   * - 自动重试：指数退避 + 抖动
   * - 续写：把已生成的 assistant 内容带回去，请模型从末尾继续
   *
   * @param {(ctx: { attempt: number, resume?: { content: string, reasoning_content: string } }) => Promise<Response>} createResponse
   * @param {(content: string, reasoning_content: string, tokens: number, speed: number) => void} updateCallback
   * @param {{ maxRetries?: number, baseDelayMs?: number, maxDelayMs?: number, jitterRatio?: number, resumeTailChars?: number }} [options]
   */
  async handleStreamResponseWithReconnect(createResponse, updateCallback, options = {}) {
    const maxRetries = options.maxRetries ?? 3
    const baseDelayMs = options.baseDelayMs ?? 500
    const maxDelayMs = options.maxDelayMs ?? 4000
    const jitterRatio = options.jitterRatio ?? 0.2

    let accumulatedContent = ''
    let accumulatedReasoning = ''
    let tokens = 0
    let speed = 0

    for (let attempt = 1; attempt <= Math.max(1, maxRetries + 1); attempt++) {
      try {
        const response = await createResponse({
          attempt,
          resume: attempt === 1 ? undefined : { content: accumulatedContent, reasoning_content: accumulatedReasoning },
        })

        // Consume this stream; reuse existing parser logic but with external state.
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        const startTime = Date.now()

        // 若重连后上游从头开始重放，这里做“前缀去重”：
        // 把新流中与已输出 accumulatedContent 的前缀相同部分跳过，直到追平后再追加。
        let dedupeActive = attempt > 1
        let matchIndex = 0

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmedLine = line.trim()
            if (!trimmedLine) continue
            if (trimmedLine === 'data: [DONE]') continue
            if (!trimmedLine.startsWith('data: ')) continue

            const jsonStr = trimmedLine.slice(6)
            if (!jsonStr || jsonStr.trim() === '') continue

            let data
            try {
              data = JSON.parse(jsonStr)
            } catch {
              continue
            }

            if (data?.error) {
              throw new Error(data.error.message || JSON.stringify(data.error))
            }

            if (data?.choices?.[0]?.delta) {
              const deltaContent = data.choices[0].delta.content || ''
              const deltaReasoning = data.choices[0].delta.reasoning_content || ''
              if (deltaContent) {
                let toAppend = deltaContent

                if (dedupeActive && accumulatedContent) {
                  // 逐字符对齐：跳过与 accumulatedContent[matchIndex:] 相同的字符
                  let i = 0
                  while (i < toAppend.length && matchIndex < accumulatedContent.length) {
                    if (toAppend[i] === accumulatedContent[matchIndex]) {
                      i += 1
                      matchIndex += 1
                      continue
                    }
                    // 一旦出现不一致，认为上游输出已偏离旧前缀，停止去重，直接追加剩余
                    dedupeActive = false
                    break
                  }

                  if (dedupeActive) {
                    toAppend = toAppend.slice(i)
                    if (matchIndex >= accumulatedContent.length) {
                      dedupeActive = false
                    }
                  }
                }

                if (toAppend) accumulatedContent += toAppend
              }
              if (deltaReasoning) accumulatedReasoning += deltaReasoning
              tokens = data.usage?.completion_tokens || tokens
              speed = Number(((tokens || 0) / ((Date.now() - startTime) / 1000)).toFixed(2))
              updateCallback(accumulatedContent, accumulatedReasoning, tokens, speed)
            }
          }
        }

        // finished normally
        return
      } catch (err) {
        if (this._isAbortError(err)) throw err
        const retryable = this._isRetryableStreamError(err)
        const isLastAttempt = attempt >= maxRetries + 1
        if (!retryable || isLastAttempt) {
          throw err
        }
        const delayMs = this._computeBackoffMs(attempt, baseDelayMs, maxDelayMs, jitterRatio)
        await this._sleep(delayMs)
      }
    }
  },

  // 处理非流式响应（防护 choices/usage 缺失或 content 为 null）
  handleNormalResponse(response, updateCallback) {
    const choices = response?.choices
    const msg = choices?.[0]?.message
    const content = msg?.content != null ? String(msg.content) : ''
    const reasoning = msg?.reasoning_content != null ? String(msg.reasoning_content) : ''
    const tokens = response?.usage?.completion_tokens ?? 0
    const speed = response?.speed ?? 0
    updateCallback(content, reasoning, tokens, speed)
  },

  // 统一的响应处理函数
  async handleResponse(response, isStream, updateCallback) {
    if (isStream) {
      await this.handleStreamResponse(response, updateCallback)
    } else {
      this.handleNormalResponse(response, updateCallback)
    }
  },
}

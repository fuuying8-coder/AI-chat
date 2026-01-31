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

import http from 'http'
import https from 'https'
import dotenv from 'dotenv'

dotenv.config()

const PORT = 3001
const API_BASE_URL = 'https://api.siliconflow.com/v1'

/**
 * 发送 JSON 响应
 */
function sendJSON(res, statusCode, data) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json',
  })
  res.end(JSON.stringify(data))
}

/**
 * 解析请求体（JSON）
 */
function parseJSONBody(req) {
  return new Promise((resolve, reject) => {
    let body = ''
    req.on('data', chunk => {
      body += chunk
    })
    req.on('end', () => {
      if (!body) return resolve({})
      try {
        resolve(JSON.parse(body))
      } catch (err) {
        reject(err)
      }
    })
  })
}

/**
 * CORS 处理
 */
function handleCORS(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')

  if (req.method === 'OPTIONS') {
    res.writeHead(204)
    res.end()
    return true
  }
  return false
}

/**
 * 主服务器
 */
const server = http.createServer(async (req, res) => {
  console.log('method =', req.method)

  // CORS
  if (handleCORS(req, res)) return

  const timestamp = new Date().toISOString()
  console.log(`[${timestamp}] ${req.method} ${req.url}`)

  try {
    // =========================
    // 健康检查
    // =========================
    if (req.method === 'GET' && req.url === '/health') {
      return sendJSON(res, 200, {
        status: 'ok',
        message: 'Server is running',
        timestamp,
        port: PORT,
      })
    }

    // =========================
    // 测试接口
    // =========================
    if (req.method === 'GET' && req.url === '/api/test') {
      return sendJSON(res, 200, {
        success: true,
        message: '后端服务连接正常！',
        timestamp,
        backendUrl: `http://localhost:${PORT}`,
      })
    }

    // =========================
    // Chat Completions
    // =========================
    if (req.method === 'POST' && req.url === '/api/chat/completions') {
      console.log('✅ 收到前端请求，正在处理...')

      const body = await parseJSONBody(req)

      const {
        model,
        messages,
        stream = false,
        max_tokens,
        temperature,
        top_p,
        top_k,
      } = body

      const apiKey =
        req.headers.authorization?.replace('Bearer ', '') ||
        body.apiKey ||
        'sk-abrsrqfqyonxoxywkfqlpmebitleomqdtjjlbpisjjatmxkq'

      const payload = {
        model,
        messages,
        stream,
        max_tokens,
        temperature,
        top_p,
        top_k,
      }

      console.log(`  📤 转发请求到: ${API_BASE_URL}/chat/completions`)

      const url = new URL(`${API_BASE_URL}/chat/completions`)
      const options = {
        hostname: url.hostname,
        port: url.port || 443,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        }
      }

      const apiReq = https.request(options, (apiRes) => {
         // 设置 SSE 响应头
          res.writeHead(apiRes.statusCode, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
          })

          // 直接将 API 响应管道传递给客户端
          apiRes.pipe(res)
      })

      apiReq.on('error', (err) => {
          console.error('API Request Error:', err)
          if (!res.headersSent) {
            sendJSON(res, 500, {
              error: {
                message: 'API request failed',
                details: err.message,
              },
            })
          }
        })

      apiReq.write(JSON.stringify(payload))
      apiReq.end()
      return
    }

    // =========================
    // 404
    // =========================
    sendJSON(res, 404, { error: 'Not Found' })

  } catch (err) {
    console.error('Server error:', err)
    sendJSON(res, 500, {
      error: {
        message: 'Internal server error',
        details: err.message,
      },
    })
  }
})

server.listen(PORT, () => {
  console.log(`🚀 Backend server is running on http://localhost:${PORT}`)
  console.log(`📡 API endpoint: http://localhost:${PORT}/api/chat/completions`)
})

import fs from 'fs'
import os from 'os'
import path from 'path'
import http from 'http'
import https from 'https'
import { spawn } from 'child_process'

const DEFAULT_TIMEOUT_SEC = 180
const DEFAULT_HEALTH_POLL_INTERVAL_MS = 500
const CANDIDATE_PORTS = [
  15920, 15921, 15922, 15923, 15924, 15925,
  26890, 26891, 26892, 26893,
  37960, 37961, 37962
]

function parseArgs(argv) {
  const args = { _: [] }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--app') args.app = argv[++i]
    else if (a === '--timeout-sec') args.timeoutSec = Number(argv[++i])
    else if (a === '--no-resource-check') args.noResourceCheck = true
    else args._.push(a)
  }
  return args
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function now() {
  return Date.now()
}

function toUrl(u) {
  return typeof u === 'string' ? new URL(u) : u
}

async function httpRequestJson(urlInput, { method = 'GET', headers = {}, body = null, timeoutMs = 8000 } = {}) {
  const url = toUrl(urlInput)
  const lib = url.protocol === 'https:' ? https : http

  return await new Promise((resolve, reject) => {
    const req = lib.request(
      {
        protocol: url.protocol,
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method,
        headers
      },
      (res) => {
        const chunks = []
        res.on('data', (c) => chunks.push(c))
        res.on('end', () => {
          const raw = Buffer.concat(chunks).toString('utf-8')
          const ok = res.statusCode && res.statusCode >= 200 && res.statusCode < 300
          if (!ok) {
            const err = new Error(`HTTP ${res.statusCode} ${method} ${url.toString()} => ${raw.slice(0, 500)}`)
            // @ts-ignore
            err.statusCode = res.statusCode
            return reject(err)
          }
          if (!raw) return resolve({ status: res.statusCode, json: null })
          try {
            return resolve({ status: res.statusCode, json: JSON.parse(raw) })
          } catch (e) {
            const err = new Error(`响应不是合法 JSON: ${raw.slice(0, 500)}`)
            return reject(err)
          }
        })
      }
    )

    req.on('error', reject)
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`请求超时 ${timeoutMs}ms: ${method} ${url.toString()}`))
    })

    if (body != null) {
      req.write(body)
    }
    req.end()
  })
}

function getMacAppExecPath(appBundlePath) {
  const macosDir = path.join(appBundlePath, 'Contents', 'MacOS')
  const entries = fs.readdirSync(macosDir, { withFileTypes: true })
  const file = entries.find(e => e.isFile())?.name
  if (!file) throw new Error(`未找到可执行文件: ${macosDir}`)
  return path.join(macosDir, file)
}

function resolveResourcesPath(appPath) {
  if (process.platform === 'darwin' && appPath.endsWith('.app')) {
    return path.join(appPath, 'Contents', 'Resources')
  }
  // Windows: <installDir>/<app>.exe 旁边有 resources/
  return path.join(path.dirname(appPath), 'resources')
}

function assertExists(p, label) {
  if (!fs.existsSync(p)) {
    throw new Error(`${label} missing: ${p}`)
  }
}

function checkPackagedResources(resourcesPath) {
  assertExists(resourcesPath, 'resourcesPath')
  const backendDir = path.join(resourcesPath, 'backend')
  const ollamaDir = path.join(resourcesPath, 'ollama')

  assertExists(backendDir, 'resources/backend')
  assertExists(ollamaDir, 'resources/ollama')

  if (process.platform === 'win32') {
    assertExists(path.join(backendDir, 'DiamondMemoryBackend.exe'), 'backend exe')
    assertExists(path.join(ollamaDir, 'ollama.exe'), 'ollama exe')
  } else if (process.platform === 'darwin') {
    assertExists(path.join(backendDir, 'DiamondMemoryBackend'), 'backend bin')
    assertExists(path.join(ollamaDir, 'ollama'), 'ollama bin')
  } else {
    assertExists(path.join(backendDir, 'DiamondMemoryBackend'), 'backend bin')
  }
}

async function readEndpointFromPortFile() {
  // 外部工具约定读取 ~/.diamond-memory/port.json
  const dmPortFile = path.join(os.homedir(), '.diamond-memory', 'port.json')
  if (!fs.existsSync(dmPortFile)) return null
  try {
    const raw = fs.readFileSync(dmPortFile, 'utf-8')
    const json = JSON.parse(raw)
    if (json?.endpoint && typeof json.endpoint === 'string') return json.endpoint
    if (json?.port && typeof json.port === 'number') return `http://127.0.0.1:${json.port}`
  } catch {
    // ignore
  }
  return null
}

async function waitForEndpoint(timeoutAt) {
  while (now() < timeoutAt) {
    const ep = await readEndpointFromPortFile()
    if (ep) return ep
    await sleep(DEFAULT_HEALTH_POLL_INTERVAL_MS)
  }
  return null
}

async function findHealthyEndpointByScan(timeoutAt) {
  while (now() < timeoutAt) {
    for (const port of CANDIDATE_PORTS) {
      const ep = `http://127.0.0.1:${port}`
      try {
        await httpRequestJson(`${ep}/health`, { timeoutMs: 1500 })
        return ep
      } catch {
        // ignore
      }
    }
    await sleep(DEFAULT_HEALTH_POLL_INTERVAL_MS)
  }
  return null
}

async function waitForHealth(endpoint, timeoutAt) {
  const healthUrl = `${endpoint}/health`
  while (now() < timeoutAt) {
    try {
      const { json } = await httpRequestJson(healthUrl, { timeoutMs: 2000 })
      if (json?.status === 'ok') return true
    } catch {
      // ignore
    }
    await sleep(DEFAULT_HEALTH_POLL_INTERVAL_MS)
  }
  return false
}

async function main() {
  const args = parseArgs(process.argv)
  const appPath = args.app
  if (!appPath) {
    console.error('Usage: node scripts/smoke/smoke_app.mjs --app <AppPath|ExePath> [--timeout-sec 180] [--no-resource-check]')
    process.exit(2)
  }

  const timeoutSec = Number.isFinite(args.timeoutSec) ? args.timeoutSec : DEFAULT_TIMEOUT_SEC
  const timeoutAt = now() + timeoutSec * 1000

  const resourcesPath = resolveResourcesPath(appPath)
  if (!args.noResourceCheck) {
    console.log(`[Smoke] resourcesPath: ${resourcesPath}`)
    checkPackagedResources(resourcesPath)
    console.log('[Smoke] resource check OK')
  }

  const execPath = (process.platform === 'darwin' && appPath.endsWith('.app'))
    ? getMacAppExecPath(appPath)
    : appPath

  console.log(`[Smoke] 启动 App: ${execPath}`)
  const child = spawn(execPath, ['--smoke-test'], {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      DM_SMOKE_TEST: '1'
    }
  })

  child.stdout.on('data', (d) => process.stdout.write(`[App] ${d}`))
  child.stderr.on('data', (d) => process.stderr.write(`[App] ${d}`))

  // 1) 优先通过 port.json 获取 endpoint
  let endpoint = await waitForEndpoint(Math.min(timeoutAt, now() + 60_000))
  // 2) 兜底：扫描常用端口
  if (!endpoint) {
    endpoint = await findHealthyEndpointByScan(Math.min(timeoutAt, now() + 60_000))
  }
  if (!endpoint) {
    child.kill()
    throw new Error('failed to discover backend endpoint')
  }

  console.log(`[Smoke] endpoint: ${endpoint}`)
  const healthy = await waitForHealth(endpoint, timeoutAt)
  if (!healthy) {
    child.kill()
    throw new Error(`backend health timeout: ${endpoint}/health`)
  }
  console.log('[Smoke] health OK')

  const marker = `__smoke_test__ ${new Date().toISOString()}`
  const createUrl = `${endpoint}/api/memory/create`
  console.log(`[Smoke] create: ${createUrl}`)
  const createBody = JSON.stringify({
    content: marker,
    category: 'smoke',
    source: 'smoke_test',
    tags: ['smoke'],
    confidence: 1.0,
    layer: 1
  })
  const { json: created } = await httpRequestJson(createUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(createBody).toString() },
    body: createBody,
    timeoutMs: 10_000
  })

  const createdId = created?.id || created?.memory_id || null
  console.log(`[Smoke] created${createdId ? ` (id=${createdId})` : ''}`)

  const queryUrl = `${endpoint}/api/memory/query?query=${encodeURIComponent(marker)}&limit=5`
  console.log(`[Smoke] query: ${queryUrl}`)
  const { json: queryResult } = await httpRequestJson(queryUrl, { timeoutMs: 10_000 })
  const memories = Array.isArray(queryResult?.memories) ? queryResult.memories : []
  const total = Number(queryResult?.total ?? queryResult?.total_candidates ?? memories.length ?? 0)
  if (!Number.isFinite(total) || total < 1 || memories.length < 1) {
    throw new Error(`query failed: expected memories.length>=1, got=${JSON.stringify(queryResult).slice(0, 500)}`)
  }
  console.log(`[Smoke] query OK: count=${memories.length}, total=${total}`)

  console.log('[Smoke] requesting app exit...')
  // 优先让 Electron 走 gracefulShutdown；不行再强杀
  try {
    child.kill('SIGTERM')
  } catch {
    try { child.kill() } catch {}
  }

  const exitOk = await Promise.race([
    new Promise(resolve => child.on('exit', () => resolve(true))),
    sleep(10_000).then(() => false)
  ])

  if (!exitOk) {
    console.warn('[Smoke] graceful exit timeout, force kill')
    try { child.kill('SIGKILL') } catch {}
  }

  console.log('[Smoke] PASS')
}

main().catch((e) => {
  console.error(`[Smoke] FAIL: ${e?.message || e}`)
  process.exit(1)
})

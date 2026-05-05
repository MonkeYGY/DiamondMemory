import { spawn, ChildProcess, execSync } from 'child_process'
import path from 'path'
import { fileURLToPath } from 'url'
import { app } from 'electron'
import fs from 'fs'
import net from 'net'
import https from 'https'
import { waitForBackendToStop } from './backend-restart-helpers.js'
import { startBackendWithBackgroundWarmup } from './backend-startup.js'
import { resolveBackendPaths } from './backend-paths.js'
import { shouldMigrateLegacySystemData } from './backend-migration.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const OLLAMA_DOWNLOAD_URLS: Record<string, string> = {
  'darwin-x64': 'https://ollama.com/download/ollama-darwin',
  'darwin-arm64': 'https://ollama.com/download/ollama-darwin-arm64',
  'win32-x64': 'https://ollama.com/download/ollama-windows-amd64.exe',
}

const OLLAMA_DOWNLOAD_MIRRORS: Record<string, string[]> = {
  'darwin-x64': [
    'https://ollama.com/download/ollama-darwin',
    'https://github.com/ollama/ollama/releases/latest/download/ollama-darwin',
    'https://mirror.ghproxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-darwin',
    'https://gh-proxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-darwin',
  ],
  'darwin-arm64': [
    'https://ollama.com/download/ollama-darwin-arm64',
    'https://github.com/ollama/ollama/releases/latest/download/ollama-darwin-arm64',
    'https://mirror.ghproxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-darwin-arm64',
    'https://gh-proxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-darwin-arm64',
  ],
  'win32-x64': [
    'https://ollama.com/download/ollama-windows-amd64.exe',
    'https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe',
    'https://mirror.ghproxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe',
    'https://gh-proxy.com/https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.exe',
  ],
}

const STABLE_DEFAULT_PORT = 15920
const MAX_CONSECUTIVE_CONFLICTS = 3
const PORT_CONFIG_FILENAME = 'port_config.json'
const PORT_FILE_VERSION = 1

interface PortConfig {
  preferred_port: number
  consecutive_conflicts: number
  last_used_port: number
}

export type BackendState = 'idle' | 'starting' | 'running' | 'error'

export class BackendManager {
  private backendProcess: ChildProcess | null = null
  private ollamaProcess: ChildProcess | null = null
  private backendPort = STABLE_DEFAULT_PORT
  private isStopping = false
  private state: BackendState = 'idle'
  private lastError = ''
  private startPromise: Promise<boolean> | null = null
  private ollamaWarmupPromise: Promise<void> | null = null
  private modelWarmupPromise: Promise<void> | null = null
  private ollamaDownloadProgress = { status: 'idle', progress: 0, downloaded: 0, total: 0 }
  private previousPort: number | null = null

  private getAutoDownloadDir(): string {
    return path.join(app.getPath('userData'), 'ollama')
  }

  private getAutoDownloadPath(): string {
    const dir = this.getAutoDownloadDir()
    if (process.platform === 'win32') {
      return path.join(dir, 'ollama.exe')
    }
    return path.join(dir, 'ollama')
  }

  private getOllamaPath(): string {
    const isDev = !app.isPackaged
    let basePath: string

    if (isDev) {
      basePath = path.resolve(__dirname, '../../../build/ollama')
    } else {
      basePath = path.join(process.resourcesPath, 'ollama')
    }

    if (process.platform === 'win32') {
      const embeddedPath = path.join(basePath, 'ollama.exe')
      if (fs.existsSync(embeddedPath) && fs.statSync(embeddedPath).size > 0) return embeddedPath
    } else {
      const embeddedPath = path.join(basePath, 'ollama')
      if (fs.existsSync(embeddedPath) && fs.statSync(embeddedPath).size > 0) return embeddedPath
    }

    const systemOllama = this.findSystemOllama()
    if (systemOllama) return systemOllama

    const autoDownloadPath = this.getAutoDownloadPath()
    return autoDownloadPath
  }

  private deployBundledOllama(): boolean {
    const isDev = !app.isPackaged
    let srcPath: string | null = null

    if (isDev) {
      srcPath = path.resolve(__dirname, '../../../build/ollama/mac/ollama')
    } else {
      const resourcesOllama = path.join(process.resourcesPath, 'ollama', 'ollama')
      if (fs.existsSync(resourcesOllama) && fs.statSync(resourcesOllama).size > 0) {
        srcPath = resourcesOllama
      }
    }

    if (!srcPath || !fs.existsSync(srcPath)) {
      console.log('[BackendManager] 内置 Ollama 不存在:', srcPath)
      return false
    }

    try {
      const targetPath = this.getAutoDownloadPath()
      const targetDir = this.getAutoDownloadDir()
      fs.mkdirSync(targetDir, { recursive: true })
      fs.copyFileSync(srcPath, targetPath)
      if (process.platform !== 'win32') {
        fs.chmodSync(targetPath, 0o755)
      }
      console.log(`[BackendManager] 内置 Ollama 部署成功: ${srcPath} -> ${targetPath} (${fs.statSync(targetPath).size} bytes)`)
      return true
    } catch (e) {
      console.error('[BackendManager] 内置 Ollama 部署失败:', e)
      return false
    }
  }

  private findSystemOllama(): string | null {
    try {
      const cmd = process.platform === 'win32' ? 'where ollama' : 'which ollama'
      const result = execSync(cmd, { encoding: 'utf-8', timeout: 5000 }).trim()
      if (result) {
        const systemPath = result.split('\n')[0].trim()
        if (systemPath && fs.existsSync(systemPath)) {
          console.log(`[BackendManager] 发现系统 Ollama: ${systemPath}`)
          return systemPath
        }
      }
    } catch {}
    return null
  }

  hasSystemOllama(): boolean {
    return this.findSystemOllama() !== null
  }

  private getOllamaModelDir(): string {
    return path.join(app.getPath('userData'), 'ollama-models')
  }

  private isValidOllamaModelsDir(dirPath: string): boolean {
    try {
      if (!dirPath) return false
      if (!fs.existsSync(dirPath)) return false
      const stat = fs.statSync(dirPath)
      if (!stat.isDirectory()) return false
      const manifestsDir = path.join(dirPath, 'manifests')
      if (!fs.existsSync(manifestsDir)) return false
      const mstat = fs.statSync(manifestsDir)
      if (!mstat.isDirectory()) return false
      return (fs.readdirSync(manifestsDir) || []).length > 0
    } catch {
      return false
    }
  }

  private detectPreferredOllamaModelsDir(): string | null {
    const envDir = (process.env.OLLAMA_MODELS || '').trim()
    if (envDir && this.isValidOllamaModelsDir(envDir)) {
      return envDir
    }

    const home = app.getPath('home')
    const candidates: string[] = []

    if (process.platform === 'win32') {
      const userProfile = (process.env.USERPROFILE || home || '').trim()
      const localAppData = (process.env.LOCALAPPDATA || '').trim()
      if (userProfile) candidates.push(path.join(userProfile, '.ollama', 'models'))
      if (localAppData) candidates.push(path.join(localAppData, 'Ollama', 'models'))
    } else {
      if (home) candidates.push(path.join(home, '.ollama', 'models'))
      if (process.platform === 'darwin' && home) {
        candidates.push(path.join(home, 'Library', 'Application Support', 'Ollama', 'models'))
      }
    }

    for (const p of candidates) {
      if (this.isValidOllamaModelsDir(p)) {
        return p
      }
    }

    return null
  }

  private getBackendPath(): string {
    const isDev = !app.isPackaged
    let basePath: string

    if (isDev) {
      basePath = path.resolve(__dirname, '../../../dist/backend')
    } else {
      basePath = path.join(process.resourcesPath, 'backend')
    }

    if (process.platform === 'win32') {
      return path.join(basePath, 'DiamondMemoryBackend.exe')
    }

    if (!isDev && process.platform === 'darwin') {
      const nuitkaDistPath = path.join(basePath, 'main.dist', 'DiamondMemoryBackend')
      if (fs.existsSync(nuitkaDistPath)) {
        try {
          fs.chmodSync(nuitkaDistPath, 0o755)
        } catch (e) {
          console.error('Failed to set Nuitka executable permissions:', e)
        }
        return nuitkaDistPath
      }
      const legacyPath = path.join(basePath, 'DiamondMemoryBackend')
      if (fs.existsSync(legacyPath)) {
        try {
          fs.chmodSync(legacyPath, 0o755)
        } catch (e) {
          console.error('Failed to set legacy executable permissions:', e)
        }
        return legacyPath
      }
      return nuitkaDistPath
    }

    return path.join(basePath, 'DiamondMemoryBackend')
  }

  private getBackendSourcePath(): string {
    return path.resolve(__dirname, '../../../backend/main.py')
  }

  private getBackendVenvPython(): string | null {
    const venvPython = path.resolve(__dirname, '../../../backend/venv/bin/python3')
    return fs.existsSync(venvPython) ? venvPython : null
  }

  private async getFreePort(): Promise<number> {
    return new Promise((resolve, reject) => {
      const server = net.createServer()
      server.listen(0, '127.0.0.1', () => {
        const port = (server.address() as net.AddressInfo).port
        server.close(() => resolve(port))
      })
      server.on('error', reject)
    })
  }

  private isPortAvailable(port: number): Promise<boolean> {
    return new Promise((resolve) => {
      const server = net.createServer()
      server.listen(port, '127.0.0.1', () => {
        server.close(() => resolve(true))
      })
      server.on('error', () => resolve(false))
    })
  }

  private getPortConfigPath(): string {
    return path.join(app.getPath('userData'), PORT_CONFIG_FILENAME)
  }

  private getUserDataPortFilePath(): string {
    return path.join(app.getPath('userData'), 'port.json')
  }

  private getHomePortFilePath(): string {
    return path.join(app.getPath('home'), '.diamond-memory', 'port.json')
  }

  private parsePortFromEndpoint(endpoint: string): number | null {
    try {
      const url = new URL(endpoint)
      const port = Number(url.port)
      return Number.isFinite(port) && port > 0 ? port : null
    } catch {
      return null
    }
  }

  private readUserDataPortFile(): { port?: number; endpoint?: string } | null {
    const userDataPortFile = this.getUserDataPortFilePath()
    try {
      if (!fs.existsSync(userDataPortFile)) return null
      const raw = fs.readFileSync(userDataPortFile, 'utf-8')
      const data = JSON.parse(raw) as { port?: unknown; endpoint?: unknown }

      const endpoint = typeof data.endpoint === 'string' ? data.endpoint : undefined
      const port = typeof data.port === 'number'
        ? data.port
        : (endpoint ? this.parsePortFromEndpoint(endpoint) ?? undefined : undefined)

      if (port === undefined && endpoint === undefined) return null
      return { port, endpoint }
    } catch {
      return null
    }
  }

  private readHomePortFile(): { port?: number; endpoint?: string } | null {
    const homePortFile = this.getHomePortFilePath()
    try {
      if (!fs.existsSync(homePortFile)) return null
      const raw = fs.readFileSync(homePortFile, 'utf-8')
      const data = JSON.parse(raw) as { port?: unknown; endpoint?: unknown }

      const endpoint = typeof data.endpoint === 'string' ? data.endpoint : undefined
      const port = typeof data.port === 'number'
        ? data.port
        : (endpoint ? this.parsePortFromEndpoint(endpoint) ?? undefined : undefined)

      if (port === undefined && endpoint === undefined) return null
      return { port, endpoint }
    } catch {
      return null
    }
  }

  /**
   * 避免旧文件误导：
   * - 外部工具读取 `~/.diamond-memory/port.json`
   * - App 内权威为 `userData/port.json`
   * 启动时若两者不一致，以 userData 覆盖 home 镜像。
   */
  private syncHomePortFileFromUserData(): void {
    const userDataPortFile = this.getUserDataPortFilePath()
    const homePortFile = this.getHomePortFilePath()

    if (!fs.existsSync(userDataPortFile)) return

    try {
      const userRaw = fs.readFileSync(userDataPortFile, 'utf-8')
      const userObj = JSON.parse(userRaw)
      if (!userObj || typeof userObj !== 'object') return

      let same = false
      try {
        if (fs.existsSync(homePortFile)) {
          const homeRaw = fs.readFileSync(homePortFile, 'utf-8')
          same = homeRaw.trim() === userRaw.trim()
        }
      } catch {
        same = false
      }

      if (!same) {
        // 统一用标准缩进写回，确保内容一致且可读
        const normalized = JSON.stringify(userObj, null, 2)
        this.atomicWriteFileSync(homePortFile, normalized)
      }
    } catch {
      // userData port.json 损坏时不做同步，避免把坏内容写到 home
    }
  }

  private atomicWriteFileSync(filePath: string, content: string): void {
    const dir = path.dirname(filePath)
    fs.mkdirSync(dir, { recursive: true })

    const tmpPath = `${filePath}.tmp-${process.pid}-${Date.now()}`
    fs.writeFileSync(tmpPath, content, 'utf-8')

    try {
      fs.renameSync(tmpPath, filePath)
    } catch {
      // Windows 上 rename 覆盖可能失败：先删除旧文件再重命名
      try {
        if (fs.existsSync(filePath)) fs.unlinkSync(filePath)
      } catch {}
      fs.renameSync(tmpPath, filePath)
    } finally {
      try {
        if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath)
      } catch {}
    }
  }

  private readPortConfig(): PortConfig {
    const configPath = this.getPortConfigPath()
    try {
      if (fs.existsSync(configPath)) {
        const data = fs.readFileSync(configPath, 'utf-8')
        const config = JSON.parse(data) as PortConfig
        return {
          preferred_port: config.preferred_port || STABLE_DEFAULT_PORT,
          consecutive_conflicts: config.consecutive_conflicts || 0,
          last_used_port: config.last_used_port || STABLE_DEFAULT_PORT
        }
      }
    } catch (e) {
      console.warn('[BackendManager] 读取端口配置失败，使用默认值:', e)
    }

    // port_config.json 不存在/损坏：尝试从端口发现文件恢复（优先 userData，再 home 镜像）
    const userData = this.readUserDataPortFile()
    const home = this.readHomePortFile()
    const fallbackPort = userData?.port ?? home?.port ?? STABLE_DEFAULT_PORT

    return {
      preferred_port: fallbackPort,
      consecutive_conflicts: 0,
      last_used_port: fallbackPort
    }
  }

  private writePortConfig(config: PortConfig): void {
    try {
      const configPath = this.getPortConfigPath()
      fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf-8')
    } catch (e) {
      console.error('[BackendManager] 写入端口配置失败:', e)
    }
  }

  private async resolveBackendPort(): Promise<number> {
    const config = this.readPortConfig()
    const preferredPort = config.preferred_port

    if (await this.isPortAvailable(preferredPort)) {
      if (config.consecutive_conflicts > 0) {
        config.consecutive_conflicts = 0
        this.writePortConfig(config)
      }
      console.log(`[BackendManager] 使用首选端口: ${preferredPort}`)
      return preferredPort
    }

    console.log(`[BackendManager] 首选端口 ${preferredPort} 被占用 (连续第 ${config.consecutive_conflicts + 1} 次)`)
    config.consecutive_conflicts += 1

    if (config.consecutive_conflicts >= MAX_CONSECUTIVE_CONFLICTS) {
      const newPort = await this.findNewStablePort(preferredPort)
      console.log(`[BackendManager] 端口连续 ${MAX_CONSECUTIVE_CONFLICTS} 次被占用，切换到新稳定端口: ${newPort}`)
      config.preferred_port = newPort
      config.consecutive_conflicts = 0
      this.writePortConfig(config)
      return newPort
    }

    this.writePortConfig(config)

    const fallbackPort = await this.getFreePort()
    console.log(`[BackendManager] 临时使用随机端口: ${fallbackPort} (首选端口冲突计数: ${config.consecutive_conflicts}/${MAX_CONSECUTIVE_CONFLICTS})`)
    return fallbackPort
  }

  private async findNewStablePort(excludePort: number): Promise<number> {
    const candidates = [
      15920, 15921, 15922, 15923, 15924, 15925,
      26890, 26891, 26892, 26893,
      37960, 37961, 37962,
    ].filter(p => p !== excludePort)

    for (const port of candidates) {
      if (await this.isPortAvailable(port)) {
        return port
      }
    }

    return this.getFreePort()
  }

  private readConfiguredStoragePath(): string | null {
    const configPath = path.join(app.getPath('userData'), 'storage-path.json')
    try {
      if (!fs.existsSync(configPath)) return null
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      if (config?.path && typeof config.path === 'string' && config.path.trim()) {
        return config.path
      }
    } catch (error) {
      console.warn('[BackendManager] 读取 storage-path.json 失败，将回退默认目录:', error)
    }
    return null
  }

  /**
   * 统一解析“系统数据目录”和“用户存储目录”
   *
   * - systemDataPath：必须固定在 userData/backend-data，用于后端运行时写入（db/索引/qdrant/temp/backups/config）
   * - storagePath：用户可变更的知识库存储路径（未配置时回退到 systemDataPath）
   */
  private getBackendRuntimePaths(): { systemDataPath: string; storagePath: string } {
    const userDataPath = app.getPath('userData')
    const configuredStoragePath = this.readConfiguredStoragePath()
    const resolved = resolveBackendPaths(userDataPath, configuredStoragePath)

    // systemDataPath：保存 db/索引/qdrant/temp/backups/config
    // - 未配置 storagePath：仍固定在 userData/backend-data（兼容旧逻辑）
    // - 配置了 storagePath：落到 storagePath/.diamond/backend-data（工作区隔离）
    // 但由于 storagePath 可能位于外置盘/网络盘，创建失败时必须回退到 userData/backend-data，避免启动失败。
    let systemDataPath = resolved.systemDataPath
    try {
      fs.mkdirSync(systemDataPath, { recursive: true })
    } catch (e) {
      console.warn('[BackendManager] 创建 systemDataPath 失败，回退到 userData/backend-data:', e)
      systemDataPath = resolveBackendPaths(userDataPath, null).systemDataPath
      fs.mkdirSync(systemDataPath, { recursive: true })
    }

    // 兼容迁移：旧版本数据默认落在 userData/backend-data。
    // 现在当用户配置了工作区时，我们将系统数据目录迁移到 storagePath/.diamond/backend-data。
    // 迁移必须“谨慎”：仅当旧目录声明的 storage_path 与当前 configuredStoragePath 一致时才迁移；
    // 否则用户切到一个新空工作区会被错误带入旧数据。
    try {
      const legacyDataPath = resolveBackendPaths(userDataPath, null).systemDataPath
      const legacyDb = path.join(legacyDataPath, 'memory.db')
      const newDb = path.join(systemDataPath, 'memory.db')
      const legacyConfigPath = path.join(legacyDataPath, 'storage_config.json')
      let legacyStoragePath = ''
      try {
        if (fs.existsSync(legacyConfigPath)) {
          const obj = JSON.parse(fs.readFileSync(legacyConfigPath, 'utf-8'))
          legacyStoragePath = String(obj?.storage_path || obj?.storagePath || '')
        }
      } catch {
        legacyStoragePath = ''
      }
      const shouldMigrate = shouldMigrateLegacySystemData({
        legacyStoragePath,
        configuredStoragePath
      })
      if (
        configuredStoragePath &&
        shouldMigrate &&
        systemDataPath !== legacyDataPath &&
        fs.existsSync(legacyDb) &&
        !fs.existsSync(newDb)
      ) {
        console.log('[BackendManager] 检测到旧数据目录存在数据库，且属于当前工作区，尝试迁移到工作区数据目录...')
        fs.mkdirSync(systemDataPath, { recursive: true })

        // 仅迁移关键文件（db + 配置），索引/向量库可在后端启动后按需重建
        for (const name of ['memory.db', 'memory.db-wal', 'memory.db-shm', 'storage_config.json']) {
          const src = path.join(legacyDataPath, name)
          const dst = path.join(systemDataPath, name)
          if (fs.existsSync(src) && !fs.existsSync(dst)) {
            fs.copyFileSync(src, dst)
          }
        }
      }
    } catch (e) {
      console.warn('[BackendManager] 迁移旧数据目录失败（可忽略）:', e)
    }

    // storagePath 允许用户自定义，但若创建失败则回退到 systemDataPath，避免启动失败
    let storagePath = resolved.storagePath
    try {
      fs.mkdirSync(storagePath, { recursive: true })
    } catch (e) {
      console.warn('[BackendManager] 创建用户存储目录失败，回退到 systemDataPath:', e)
      storagePath = systemDataPath
    }

    return { systemDataPath, storagePath }
  }

  async startOllama(): Promise<boolean> {
    const ollamaPath = this.getOllamaPath()
    const hasValidLocalOllama = (() => {
      try { return fs.existsSync(ollamaPath) && fs.statSync(ollamaPath).size > 0 } catch { return false }
    })()
    const isSystemOllama = this.findSystemOllama() === ollamaPath

    if (hasValidLocalOllama) {
      console.log(`[BackendManager] 发现 Ollama: ${ollamaPath}${isSystemOllama ? ' (系统安装)' : ''}`)
      if (process.platform !== 'win32' && !isSystemOllama) {
        try {
          fs.chmodSync(ollamaPath, 0o755)
        } catch (e) {
          console.error('[BackendManager] 设置 Ollama 可执行权限失败:', e)
        }
      }
    } else if (!isSystemOllama && ollamaPath) {
      try {
        if (fs.existsSync(ollamaPath) && fs.statSync(ollamaPath).size === 0) {
          fs.unlinkSync(ollamaPath)
          console.log('[BackendManager] 清理空壳 Ollama 文件:', ollamaPath)
        }
      } catch (e) {
        console.warn('[BackendManager] 清理空壳文件失败:', e)
      }
      console.log('[BackendManager] 未发现有效的 Ollama，尝试从内置路径部署...')
      const deployed = this.deployBundledOllama()
      if (!deployed) {
        console.log('[BackendManager] 内置部署失败，尝试自动下载...')
        const downloaded = await this.downloadOllama()
        if (!downloaded) {
          console.log('[BackendManager] 自动下载失败，将尝试使用系统 Ollama')
        }
      }
    }

    const isOllamaRunning = await this.checkOllamaRunning()
    if (isOllamaRunning) {
      console.log('[BackendManager] Ollama 服务已在运行')
    } else {
      const finalOllamaPath = this.getOllamaPath()
      const hasLocalOllama = (() => {
        try { return fs.existsSync(finalOllamaPath) && fs.statSync(finalOllamaPath).size > 0 } catch { return false }
      })()
      const ollamaExe = hasLocalOllama ? finalOllamaPath : 'ollama'

      const legacyModelsDir = this.detectPreferredOllamaModelsDir()
      const userDataModelsDir = this.getOllamaModelDir()
      const preferredModelsDir = legacyModelsDir || userDataModelsDir
      fs.mkdirSync(preferredModelsDir, { recursive: true })
      if (legacyModelsDir) {
        console.log(`[BackendManager] 发现旧模型目录，复用: ${legacyModelsDir}`)
      }

      const startOnce = async (modelsDir: string): Promise<boolean> => {
        return await new Promise<boolean>((resolve) => {
          try {
            const env: Record<string, string> = {
              ...process.env as Record<string, string>,
              OLLAMA_HOST: '127.0.0.1:11434',
              OLLAMA_MODELS: modelsDir,
            }

            this.ollamaProcess = this.spawnProcessForTest(ollamaExe, ['serve'], {
              cwd: hasLocalOllama ? path.dirname(ollamaExe) : undefined,
              stdio: ['pipe', 'pipe', 'pipe'],
              detached: false,
              env
            })

            this.ollamaProcess.stdout?.on('data', (data: Buffer) => {
              console.log(`[Ollama] ${data.toString().trim()}`)
            })

            this.ollamaProcess.stderr?.on('data', (data: Buffer) => {
              console.error(`[Ollama Error] ${data.toString().trim()}`)
            })

            this.ollamaProcess.on('exit', (code, signal) => {
              console.log(`[Ollama] 进程退出，退出码: ${code}, 信号: ${signal}`)
              this.ollamaProcess = null
            })

            this.ollamaProcess.on('error', (err) => {
              console.error('[Ollama Process Error]', err)
              this.ollamaProcess = null
              resolve(false)
            })

            this.waitForOllama().then(resolve)
          } catch (e) {
            console.error('[BackendManager] 启动 Ollama 失败:', e)
            resolve(false)
          }
        })
      }

      let started = await startOnce(preferredModelsDir)
      if (!started && legacyModelsDir) {
        try {
          this.ollamaProcess?.kill()
        } catch {}
        this.ollamaProcess = null
        fs.mkdirSync(userDataModelsDir, { recursive: true })
        console.warn('[BackendManager] 使用旧模型目录启动失败，回退到 userData/ollama-models 重试')
        started = await startOnce(userDataModelsDir)
      }

      if (!started) return false
    }

    return true
  }

  private async downloadOllama(): Promise<boolean> {
    const platformKey = `${process.platform}-${process.arch}`
    const urls = OLLAMA_DOWNLOAD_MIRRORS[platformKey] || [OLLAMA_DOWNLOAD_URLS[platformKey]].filter(Boolean)
    if (!urls.length) {
      console.error(`[BackendManager] 不支持的平台: ${platformKey}`)
      return false
    }

    const targetPath = this.getAutoDownloadPath()
    if (fs.existsSync(targetPath)) return true

    const targetDir = this.getAutoDownloadDir()
    fs.mkdirSync(targetDir, { recursive: true })

    for (let urlIdx = 0; urlIdx < urls.length; urlIdx++) {
      const url = urls[urlIdx]
      if (this.ollamaDownloadProgress.status === 'cancelled') return false

      this.ollamaDownloadProgress = { status: 'downloading', progress: 0, downloaded: 0, total: 0 }
      console.log(`[BackendManager] 尝试下载 Ollama (源${urlIdx + 1}/${urls.length}): ${url}`)

      try {
        const downloaded = await new Promise<boolean>((resolve) => {
          const tempPath = targetPath + '.download'

          https.get(url, { timeout: 30000 }, (response) => {
            if (response.statusCode === 301 || response.statusCode === 302) {
              const redirectUrl = response.headers.location
              if (redirectUrl) {
                https.get(redirectUrl, { timeout: 600000 }, (redirectResponse) => {
                  this._handleDownloadStream(redirectResponse, tempPath, targetPath, resolve)
                }).on('error', (err) => {
                  console.error(`[BackendManager] 重定向下载失败(源${urlIdx + 1}):`, err)
                  resolve(false)
                })
                return
              }
            }
            this._handleDownloadStream(response, tempPath, targetPath, resolve)
          }).on('error', (err) => {
            console.error(`[BackendManager] 下载失败(源${urlIdx + 1}):`, err)
            resolve(false)
          })
        })

        if (downloaded) return true
      } catch (e) {
        console.error(`[BackendManager] 下载异常(源${urlIdx + 1}):`, e)
      }
    }

    this.ollamaDownloadProgress.status = 'failed'
    console.error('[BackendManager] 所有下载源均失败')
    return false
  }

  private _handleDownloadStream(
    response: any,
    tempPath: string,
    targetPath: string,
    resolve: (value: boolean) => void
  ) {
    const totalSize = parseInt(response.headers['content-length'] || '0', 10)
    let downloaded = 0
    const startTime = Date.now()

    const file = fs.createWriteStream(tempPath)

    response.on('data', (chunk: Buffer) => {
      downloaded += chunk.length
      file.write(chunk)

      const progress = totalSize > 0 ? Math.min(Math.round(downloaded / totalSize * 100), 99) : 0
      const elapsed = (Date.now() - startTime) / 1000
      const speed = elapsed > 0 ? (downloaded / elapsed / 1024 / 1024).toFixed(1) + ' MB/s' : ''

      this.ollamaDownloadProgress = {
        status: 'downloading',
        progress,
        downloaded,
        total: totalSize,
      }

      if (progress % 10 === 0) {
        console.log(`[BackendManager] 下载进度: ${progress}% (${speed})`)
      }
    })

    response.on('end', () => {
      file.end(() => {
        if (fs.existsSync(targetPath)) {
          fs.unlinkSync(targetPath)
        }
        fs.renameSync(tempPath, targetPath)

        if (process.platform !== 'win32') {
          try { fs.chmodSync(targetPath, 0o755) } catch {}
        }

        this.ollamaDownloadProgress = { status: 'completed', progress: 100, downloaded, total: totalSize }
        console.log(`[BackendManager] Ollama 下载完成: ${targetPath}`)
        resolve(true)
      })
    })

    response.on('error', (err: Error) => {
      console.error('[BackendManager] 下载流错误:', err)
      file.close()
      if (fs.existsSync(tempPath)) {
        try { fs.unlinkSync(tempPath) } catch {}
      }
      this.ollamaDownloadProgress.status = 'failed'
      resolve(false)
    })
  }

  getOllamaDownloadProgress() {
    return this.ollamaDownloadProgress
  }

  private async checkOllamaRunning(): Promise<boolean> {
    try {
      const response = await fetch('http://127.0.0.1:11434/api/tags', {
        signal: AbortSignal.timeout(3000)
      })
      return response.ok
    } catch {
      return false
    }
  }

  private async waitForOllama(maxRetries = 30): Promise<boolean> {
    for (let i = 0; i < maxRetries; i++) {
      if (await this.checkOllamaRunning()) {
        console.log('[BackendManager] Ollama 服务已就绪')
        return true
      }
      console.log(`[BackendManager] 等待 Ollama 启动... (${i + 1}/${maxRetries})`)
      await new Promise(resolve => setTimeout(resolve, 1000))
    }
    console.error('[BackendManager] Ollama 启动超时')
    return false
  }

  private async ensureOllamaWarmup(): Promise<void> {
    if (this.ollamaWarmupPromise) {
      return this.ollamaWarmupPromise
    }

    this.ollamaWarmupPromise = (async () => {
      const ollamaReady = await this.startOllama()
      if (!ollamaReady) {
        return
      }
      await this.waitForOllama()
    })()

    try {
      await this.ollamaWarmupPromise
    } finally {
      if (this.ollamaWarmupPromise && this.modelWarmupPromise === null) {
        this.ollamaWarmupPromise = null
      }
    }
  }

  protected spawnProcessForTest(command: string, args: string[], options: Parameters<typeof spawn>[2]) {
    return spawn(command, args, options)
  }

  private triggerModelWarmup(ollamaWarmupPromise: Promise<void>): void {
    if (this.modelWarmupPromise) {
      return
    }

    this.modelWarmupPromise = ollamaWarmupPromise
      .then(async () => {
        await this.warmupModels()
      })
      .catch((error) => {
        console.warn('[BackendManager] 模型后台预热失败:', error)
      })
      .finally(() => {
        this.modelWarmupPromise = null
        this.ollamaWarmupPromise = null
      })
  }

  private async warmupModels(): Promise<void> {
    try {
      await fetch(`http://127.0.0.1:${this.backendPort}/api/config/preload-models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(10000)
      })
    } catch (error) {
      console.warn('[BackendManager] 后台模型预热触发失败:', error)
    }
  }

  async startBackend(): Promise<boolean> {
    if (this.startPromise) {
      return this.startPromise
    }

    if (this.backendProcess) {
      const isRunning = await this.isBackendRunning()
      if (isRunning) {
        this.state = 'running'
        return true
      }
    }

    this.startPromise = (async () => {
      // 启动早期同步一次：确保外部工具读取的 home 镜像不被旧文件误导
      try {
        this.syncHomePortFileFromUserData()
      } catch {}

      this.state = 'starting'
      this.lastError = ''

      const { systemDataPath, storagePath } = this.getBackendRuntimePaths()

      const isDev = !app.isPackaged
      const backendMode = String(process.env.DM_BACKEND_MODE || 'electron').toLowerCase()

      // 开发模式可选：仅连接外部源码后端（由脚本启动），禁止 Electron 自启动后端，避免“双后端/双端口/双数据源”
      if (backendMode === 'python') {
        const portFromEnv = Number(process.env.DM_BACKEND_PORT || STABLE_DEFAULT_PORT)
        const port = Number.isFinite(portFromEnv) && portFromEnv > 0 ? portFromEnv : STABLE_DEFAULT_PORT

        this.previousPort = this.backendPort
        this.backendPort = port

        console.log(`[BackendManager] DM_BACKEND_MODE=python：不自启动后端，仅连接现有后端 (port=${port})`)
        const ok = await this.waitForBackend()
        if (ok) {
          this.state = 'running'
          this.lastError = ''
          this.writePortFile()

          if (this.previousPort !== null && this.previousPort !== this.backendPort) {
            console.log(`[BackendManager] 端口已变更: ${this.previousPort} -> ${this.backendPort}，触发AI软件配置更新`)
            this.notifyPortChange(this.previousPort, this.backendPort)
          }
        } else {
          this.state = 'error'
          this.lastError = `外部后端未就绪 (port=${port})`
        }
        return ok
      }

      let command: string
      let cwd: string
      let buildArgsForPort: (port: number) => string[]

      if (isDev) {
        const sourcePath = this.getBackendSourcePath()
        if (!fs.existsSync(sourcePath)) {
          console.error(`[BackendManager] 后端源码不存在: ${sourcePath}`)
          this.state = 'error'
          this.lastError = `后端源码不存在: ${sourcePath}`
          return false
        }

        const venvPython = this.getBackendVenvPython()
        const pythonCmd = venvPython || (process.platform === 'win32' ? 'python' : 'python3')

        command = pythonCmd
        buildArgsForPort = (port: number) => [
          sourcePath,
          '--port',
          port.toString(),
          '--data-dir',
          systemDataPath,
          '--storage-path',
          storagePath
        ]
        cwd = path.dirname(sourcePath)

        console.log(`[BackendManager] 开发模式: 直接运行 Python 源码 (0 编译等待)`)
        console.log(`[BackendManager] Python: ${command}`)
        console.log(`[BackendManager] 源码: ${sourcePath}`)
      } else {
        const backendPath = this.getBackendPath()
        command = backendPath
        buildArgsForPort = (port: number) => [
          '--port',
          port.toString(),
          '--data-dir',
          systemDataPath,
          '--storage-path',
          storagePath
        ]
        cwd = path.dirname(backendPath)

        console.log(`[BackendManager] 生产模式: 运行 Nuitka 编译产物`)
        console.log(`[BackendManager] 后端: ${backendPath}`)
      }

      console.log(`[BackendManager] systemDataPath(--data-dir): ${systemDataPath}`)
      console.log(`[BackendManager] storagePath(--storage-path): ${storagePath}`)

      const env: Record<string, string> = {
        ...process.env as Record<string, string>,
        PYTHONIOENCODING: 'utf-8',
        PYTHONDONTWRITEBYTECODE: '1',
        PYTHONUNBUFFERED: '1',
        ELECTRON_RESOURCES_PATH: process.resourcesPath,
        RESOURCE_PATH: process.resourcesPath,
        DM_USER_DATA_DIR: app.getPath('userData'),
        DM_MANAGED_BY_ELECTRON: '1',
        DM_DISABLE_OLLAMA_AUTOSTART: '1'
      }

      if (isDev) {
        const venvPath = path.resolve(__dirname, '../../../backend/venv/bin')
        if (fs.existsSync(venvPath)) {
          const sep = process.platform === 'win32' ? ';' : ':'
          env.PATH = venvPath + sep + (env.PATH || '')
        }
      }

      const startup = await startBackendWithBackgroundWarmup({
        existingWarmupPromise: this.ollamaWarmupPromise,
        startWarmup: async () => {
          await this.ensureOllamaWarmup()
        },
        resolvePort: async () => {
          const port = await this.resolveBackendPort()
          this.previousPort = this.backendPort
          console.log(`[BackendManager] 解析端口: ${port}`)
          return port
        },
        spawnBackend: async (port: number) => {
          this.backendPort = port
          this.backendProcess = this.spawnProcessForTest(command, buildArgsForPort(port), {
            cwd,
            stdio: ['pipe', 'pipe', 'pipe'],
            detached: false,
            env
          })

          this.backendProcess.stdout?.on('data', (data: Buffer) => {
            console.log(`[Backend] ${data.toString().trim()}`)
          })

          this.backendProcess.stderr?.on('data', (data: Buffer) => {
            console.error(`[Backend Error] ${data.toString().trim()}`)
          })

          this.backendProcess.on('exit', (code: number | null, signal: NodeJS.Signals | null) => {
            if (!this.isStopping) {
              this.state = 'error'
              this.lastError = `后端异常退出，退出码: ${code}, 信号: ${signal}`
              console.error(`[Backend] 异常退出，退出码: ${code}, 信号: ${signal}`)
            }
            this.backendProcess = null
          })

          this.backendProcess.on('error', (err: Error) => {
            this.state = 'error'
            this.lastError = err.message
            console.error('[Backend Process Error] 启动或运行后端进程时发生错误:', err)
          })
        },
        waitForBackend: async () => {
          return this.waitForBackend()
        }
      })

      const isReady = startup.ready
      if (isReady) {
        this.state = 'running'
        this.lastError = ''
        this.writePortFile()
        this.triggerModelWarmup(startup.warmupPromise)

        if (this.previousPort !== null && this.previousPort !== this.backendPort) {
          console.log(`[BackendManager] 端口已变更: ${this.previousPort} -> ${this.backendPort}，触发AI软件配置更新`)
          this.notifyPortChange(this.previousPort, this.backendPort)
        }

        console.log('[BackendManager] 后端启动成功！')
      } else {
        this.state = 'error'
        if (!this.lastError) {
          this.lastError = '后端启动超时'
        }
        console.error('[BackendManager] 后端启动超时')
      }

      return isReady
    })()

    try {
      return await this.startPromise
    } finally {
      this.startPromise = null
    }
  }

  private async waitForBackend(maxRetries = 120): Promise<boolean> {
    for (let i = 0; i < maxRetries; i++) {
      try {
        const response = await fetch(`http://127.0.0.1:${this.backendPort}/health`)
        if (response.ok) {
          return true
        }
      } catch {
        // 后端还未就绪
      }
      console.log(`[BackendManager] 等待后端启动... (${i + 1}/${maxRetries})`)
      await new Promise(resolve => setTimeout(resolve, 500))
    }
    return false
  }

  private async unloadOllamaModels(): Promise<void> {
    try {
      const response = await fetch('http://127.0.0.1:11434/api/ps', {
        signal: AbortSignal.timeout(3000)
      })
      if (response.ok) {
        const data = await response.json() as { models?: { name: string }[] }
        const models = data.models || []
        for (const model of models) {
          try {
            await fetch('http://127.0.0.1:11434/api/generate', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ model: model.name, keep_alive: 0 }),
              signal: AbortSignal.timeout(5000)
            })
            console.log(`[BackendManager] 已卸载模型: ${model.name}`)
          } catch (e) {
            console.error(`[BackendManager] 卸载模型 ${model.name} 失败:`, e)
          }
        }
      }
    } catch (e) {
      console.error('[BackendManager] 获取运行中模型列表失败:', e)
    }
  }

  async gracefulShutdown(): Promise<void> {
    console.log('[BackendManager] 优雅关闭：卸载大模型并停止所有服务...')
    await this.unloadOllamaModels()
    await this.stopBackend({ stopOllama: true })
  }

  async stopBackend(options?: { stopOllama?: boolean }): Promise<void> {
    this.isStopping = true
    const stopOllama = options?.stopOllama !== false
    const previousPort = this.backendPort
    const backendProcess = this.backendProcess
    const ollamaProcess = this.ollamaProcess

    if (this.backendProcess) {
      console.log('[BackendManager] 正在停止后端服务...')
      if (process.platform === 'win32') {
        this.backendProcess.kill()
        try {
          const { execSync } = require('child_process')
          execSync(`taskkill /pid ${this.backendProcess.pid} /T /F`, { stdio: 'ignore' })
        } catch {
          this.backendProcess.kill()
        }
      } else {
        this.backendProcess.kill('SIGTERM')
        setTimeout(() => {
          if (this.backendProcess) {
            this.backendProcess.kill('SIGKILL')
          }
        }, 5000)
      }
    }

    const backendStopped = await waitForBackendToStop(
      async () => {
        try {
          const response = await fetch(`http://127.0.0.1:${previousPort}/health`)
          return response.ok
        } catch {
          return false
        }
      },
      { pollMs: 250, maxAttempts: 40 }
    )

    this.backendProcess = null
    if (backendProcess && backendStopped) {
      console.log('[BackendManager] 后端服务已停止')
    } else if (backendProcess) {
      console.warn('[BackendManager] 后端停止超时，继续执行后续流程')
    }

    if (ollamaProcess && stopOllama) {
      console.log('[BackendManager] 正在停止 Ollama 服务...')
      if (process.platform === 'win32') {
        ollamaProcess.kill()
        try {
          const { execSync } = require('child_process')
          execSync(`taskkill /pid ${ollamaProcess.pid} /T /F`, { stdio: 'ignore' })
        } catch {
          ollamaProcess.kill()
        }
        this.ollamaProcess = null
      } else {
        ollamaProcess.kill('SIGTERM')
        await new Promise<void>((resolve) => {
          const timeout = setTimeout(() => {
            console.warn('[BackendManager] Ollama SIGTERM 超时，发送 SIGKILL')
            try { ollamaProcess.kill('SIGKILL') } catch {}
            resolve()
          }, 8000)
          ollamaProcess.once('exit', () => {
            clearTimeout(timeout)
            resolve()
          })
          ollamaProcess.once('error', () => {
            clearTimeout(timeout)
            resolve()
          })
        })
        this.ollamaProcess = null
      }
      console.log('[BackendManager] Ollama 服务已停止')
    } else if (ollamaProcess) {
      console.log('[BackendManager] 本次仅重启后端，不停止 Ollama 服务')
    }

    this.state = 'idle'
    this.lastError = ''
    this.startPromise = null
    this.isStopping = false
  }

  async isBackendRunning(): Promise<boolean> {
    try {
      const response = await fetch(`http://127.0.0.1:${this.backendPort}/health`)
      return response.ok
    } catch {
      return false
    }
  }

  getPort(): number {
    return this.backendPort
  }

  getStatus() {
    return {
      isRunning: this.state === 'running',
      state: this.state,
      port: this.backendPort,
      lastError: this.lastError
    }
  }

  getOllamaExePath(): string {
    return this.getOllamaPath()
  }

  hasEmbeddedOllama(): boolean {
    return fs.existsSync(this.getOllamaPath())
  }

  getUserDataPath(): string {
    return app.getPath('userData')
  }

  getStorageInfo(): { userDataPath: string; ollamaPath: string; ollamaModelPath: string; backendDataPath: string } {
    const { systemDataPath } = this.getBackendRuntimePaths()
    return {
      userDataPath: app.getPath('userData'),
      ollamaPath: this.getAutoDownloadDir(),
      ollamaModelPath: this.getOllamaModelDir(),
      backendDataPath: systemDataPath
    }
  }

  private writePortFile(): void {
    const nowIso = new Date().toISOString()
    const portPayload = {
      version: PORT_FILE_VERSION,
      updatedAt: nowIso,
      port: this.backendPort,
      pid: process.pid,
      startedAt: nowIso,
      endpoint: `http://127.0.0.1:${this.backendPort}`
    }

    const portData = JSON.stringify(portPayload, null, 2)

    // 1) userData/port.json：给 App 内部与调试用，尽力写入
    try {
      const userDataPortFile = this.getUserDataPortFilePath()
      this.atomicWriteFileSync(userDataPortFile, portData)
      console.log(`[BackendManager] 端口信息已写入: ${userDataPortFile}`)
    } catch (e) {
      console.error('[BackendManager] 写入 userData 端口文件失败:', e)
    }

    // 2) ~/.diamond-memory/port.json：兼容外部生态，写失败不影响 App 启动
    try {
      const dmPortFile = this.getHomePortFilePath()
      this.atomicWriteFileSync(dmPortFile, portData)
      console.log(`[BackendManager] 端口信息已写入: ${dmPortFile}`)
    } catch (e) {
      console.warn('[BackendManager] 写入 ~/.diamond-memory/port.json 失败（不影响 App 启动）:', e)
    }

    // 3) 更新 port_config.json 的 last_used_port（不依赖上面两次写入成功与否）
    try {
      const config = this.readPortConfig()
      config.last_used_port = this.backendPort
      this.writePortConfig(config)
    } catch (e) {
      console.warn('[BackendManager] 更新 last_used_port 失败（不影响 App 启动）:', e)
    }
  }

  private async notifyPortChange(oldPort: number, newPort: number): Promise<void> {
    try {
      await fetch(`http://127.0.0.1:${newPort}/api/config/refresh-ai-integrations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_port: oldPort, new_port: newPort }),
        signal: AbortSignal.timeout(10000)
      })
      console.log('[BackendManager] AI软件集成配置更新请求已发送')
    } catch (e) {
      console.warn('[BackendManager] AI软件集成配置更新请求失败:', e)
    }
  }
}

export const backendManager = new BackendManager()

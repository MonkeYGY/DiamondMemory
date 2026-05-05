import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron'
import path from 'path'
import fs from 'fs'
import { spawn, type ChildProcess, type SpawnOptions } from 'child_process'
import { fileURLToPath } from 'url'
import { backendManager } from './backend-manager.js'
import { performControlledBackendRestart } from './backend-restart-helpers.js'
import { updateManager } from './update-manager.js'
import { registerHttpProxyIpcHandlers } from './http-ipc-proxy.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

let mainWindow: BrowserWindow | null = null
let isQuitting = false
let isUninstalling = false
const isSmokeTest = process.argv.includes('--smoke-test') || process.env.DM_SMOKE_TEST === '1'
const appRunId = `${Date.now()}-${Math.random().toString(16).slice(2)}`
let isFirstRunCached: boolean | null = null

if (process.env.NODE_ENV === 'development' || !app.isPackaged) {
  app.commandLine.appendSwitch('disable-features', 'OutOfBlinkCors')
}

async function confirmDangerousAction(options: {
  title: string
  message: string
  detail?: string
  confirmText?: string
}): Promise<boolean> {
  // 冒烟测试/无窗口场景下不要阻塞
  if (isSmokeTest) return true
  if (!mainWindow || mainWindow.isDestroyed()) return true

  const result = await dialog.showMessageBox(mainWindow, {
    type: 'warning',
    title: options.title,
    message: options.message,
    detail: options.detail,
    buttons: ['取消', options.confirmText || '确定'],
    defaultId: 0,
    cancelId: 0,
    noLink: true
  })

  return result.response === 1
}

function validateStoragePath(storagePath: string): string {
  if (typeof storagePath !== 'string') throw new Error('存储路径无效')
  const trimmed = storagePath.trim()
  if (!trimmed) throw new Error('存储路径不能为空')
  if (trimmed.includes('\0')) throw new Error('存储路径包含非法字符')
  const resolved = path.resolve(trimmed)
  if (!path.isAbsolute(resolved)) throw new Error('存储路径必须是绝对路径')

  // 禁止设置为根目录（极易误操作导致扫描/读取敏感文件）
  const parsed = path.parse(resolved)
  if (parsed.root && path.resolve(parsed.root) === resolved) {
    throw new Error('禁止将存储路径设置为磁盘根目录')
  }
  return resolved
}

function spawnWithTimeout(
  command: string,
  args: string[],
  opts: SpawnOptions = {},
  timeoutMs: number
): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const proc: ChildProcess = spawn(command, args, opts)
    let stdout = ''
    let stderr = ''
    const timer = setTimeout(() => {
      try {
        proc.kill('SIGKILL')
      } catch {}
      reject(new Error(`命令超时(${timeoutMs}ms): ${command}`))
    }, timeoutMs)

    proc.stdout?.on('data', (d: Buffer) => {
      stdout += d.toString()
    })
    proc.stderr?.on('data', (d: Buffer) => {
      stderr += d.toString()
    })
    proc.on('error', (err: Error) => {
      clearTimeout(timer)
      reject(err)
    })
    proc.on('close', (code: number | null) => {
      clearTimeout(timer)
      resolve({ code: typeof code === 'number' ? code : -1, stdout, stderr })
    })
  })
}

function getBackendStoragePath(): string {
  const configPath = path.join(app.getPath('userData'), 'storage-path.json')
  try {
    if (fs.existsSync(configPath)) {
      const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      if (config.path) {
        return config.path
      }
    }
  } catch (error) {
    console.error('[Main] 读取存储配置失败:', error)
  }
  return path.join(app.getPath('userData'), 'backend-data')
}

function getSystemDataPath(): string {
  return path.join(app.getPath('userData'), 'backend-data')
}

function createWindow(): void {
  const isMac = process.platform === 'darwin'

  const windowOptions: Electron.BrowserWindowConstructorOptions = {
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    show: !isSmokeTest,
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  }

  if (isMac) {
    windowOptions.titleBarStyle = 'hiddenInset'
  } else {
    windowOptions.frame = true
  }

  mainWindow = new BrowserWindow(windowOptions)

  // 安全：禁止渲染进程导航到外部站点；外链统一交给系统浏览器打开
  const isAllowedNavigationUrl = (targetUrl: string): boolean => {
    try {
      // 开发环境：允许 Vite dev server
      if (process.env.NODE_ENV === 'development' || !app.isPackaged) {
        return /^https?:\/\/(localhost|127\.0\.0\.1):5173(\/|$)/.test(targetUrl)
      }
      // 生产环境：仅允许 file:// / app:// / about:blank
      return /^(file:\/\/|app:\/\/|about:blank$)/.test(targetUrl)
    } catch {
      return false
    }
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url).catch(() => {})
    }
    return { action: 'deny' }
  })

  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (isAllowedNavigationUrl(url)) return
    event.preventDefault()
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url).catch(() => {})
    }
  })

  // 冒烟测试模式：尽可能减少 UI/更新相关副作用，避免阻塞“干净机”自动化
  if (!isSmokeTest) {
    updateManager.initialize(mainWindow)
  }

  if (process.env.NODE_ENV === 'development' || !app.isPackaged) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
  }

  mainWindow.on('close', (event) => {
    if (process.platform === 'darwin' && !isQuitting) {
      event.preventDefault()
      mainWindow?.hide()
      return
    }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  mainWindow.webContents.on('did-finish-load', async () => {
    try {
      const hasBridge = await mainWindow?.webContents.executeJavaScript(
        'typeof window.electronAPI !== "undefined"'
      )
      console.log('[Main] electronAPI bridge loaded:', hasBridge)
    } catch (error) {
      console.error('[Main] 检查 electronAPI bridge 失败:', error)
    }
  })
}

app.whenReady().then(() => {
  console.log('[Main] 钻石记忆系统启动')

  // 冒烟测试模式：不需要窗口也能完成“启动→后端可用→API调用→退出”
  if (!isSmokeTest) {
    // Create window immediately for better UX
    createWindow()
  }

  // 注册“渲染进程 -> IPC -> 主进程 -> 本机后端”的请求代理（生产环境彻底绕开 CORS）
  registerHttpProxyIpcHandlers({
    getWebContents: () => mainWindow?.webContents || null
  })

  // Start backend asynchronously
  backendManager.startBackend().then(backendStarted => {
    if (!backendStarted) {
      console.error('[Main] 后端启动失败，但继续运行前端')
    }
  }).catch(e => {
    console.error('[Main] 后端启动异常:', e)
  })

  app.on('activate', () => {
    if (isQuitting) return
    if (mainWindow) {
      mainWindow.show()
      mainWindow.focus()
    } else {
      if (!isSmokeTest) {
        createWindow()
      }
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// 冒烟测试脚本通过 SIGTERM/SIGINT 请求退出时，走应用既有的 gracefulShutdown 链路
process.on('SIGTERM', () => {
  if (!isQuitting) app.quit()
})
process.on('SIGINT', () => {
  if (!isQuitting) app.quit()
})

app.on('before-quit', (event) => {
  if (isQuitting) return
  if (isUninstalling) return
  event.preventDefault()
  isQuitting = true
  console.log('[Main] 应用退出，清理资源...')
  const shutdownTimeout = setTimeout(() => {
    console.warn('[Main] 后端关闭超时，强制退出')
    app.quit()
  }, 10000)
  backendManager.gracefulShutdown().then(() => {
    clearTimeout(shutdownTimeout)
    app.quit()
  }).catch(() => {
    clearTimeout(shutdownTimeout)
    app.quit()
  })
})

// IPC Handlers
ipcMain.handle('backend:status', async () => {
  const isRunning = await backendManager.isBackendRunning()
  const status = backendManager.getStatus()
  return {
    ...status,
    isRunning,
    port: backendManager.getPort()
  }
})

ipcMain.handle('backend:restart', async () => {
  return await performControlledBackendRestart({
    // 重启核心服务时，默认仅重启后端，不停止 Ollama，避免“重启比新打开还慢 / 模型重载”的体验问题
    // 若需要完整重启（含 Ollama），由 app 退出链路 gracefulShutdown 负责
    stopBackend: () => backendManager.stopBackend({ stopOllama: false }),
    startBackend: () => backendManager.startBackend()
  })
})

ipcMain.handle('backend:stop', async () => {
  await backendManager.stopBackend()
  return true
})

ipcMain.handle('app:info', () => ({
  platform: process.platform,
  version: app.getVersion(),
  isPackaged: app.isPackaged
}))

ipcMain.handle('app:runId', () => appRunId)

ipcMain.handle('app:isFirstRun', () => {
  if (typeof isFirstRunCached === 'boolean') return isFirstRunCached
  const markerPath = path.join(app.getPath('userData'), 'first-run.json')
  try {
    const exists = fs.existsSync(markerPath)
    isFirstRunCached = !exists
    if (!exists) {
      fs.writeFileSync(markerPath, JSON.stringify({ firstRunAt: new Date().toISOString() }), 'utf-8')
    }
  } catch {
    isFirstRunCached = false
  }
  return isFirstRunCached
})

// 切换工作区/路径后若出现“后端重启超时/服务断开”反复，提供全量重启兜底：重启整个 Electron 应用
ipcMain.handle('app:relaunch', async () => {
  try {
    // 尽力优雅关闭（包含卸载模型），避免残留进程
    await backendManager.gracefulShutdown()
  } catch (e) {
    console.warn('[Main] relaunch 前优雅关闭失败（可忽略）:', e)
  }

  try {
    app.relaunch()
  } catch (e) {
    console.error('[Main] app.relaunch 失败:', e)
    return false
  }

  // 让 IPC 返回后再退出，避免调用端卡住
  setTimeout(() => {
    try {
      app.exit(0)
    } catch {}
  }, 50)
  return true
})

ipcMain.handle('window:minimize', () => {
  mainWindow?.minimize()
  return true
})

ipcMain.handle('window:maximize', () => {
  mainWindow?.maximize()
  return true
})

ipcMain.handle('window:toggleMaximize', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize()
  } else {
    mainWindow?.maximize()
  }
  return true
})

ipcMain.handle('window:close', () => {
  mainWindow?.close()
  return true
})

ipcMain.handle('dialog:selectDirectory', async (_event, options?: { title?: string }) => {
  const title = options?.title || '选择存储路径'
  const result = await dialog.showOpenDialog(mainWindow!, { properties: ['openDirectory'], title })
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0]
  }
  return null
})

ipcMain.handle('storage:getPath', () => {
  const configPath = path.join(app.getPath('userData'), 'storage-path.json')
  try {
    if (fs.existsSync(configPath)) {
      const data = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      return data.path || ''
    }
  } catch (error) {
    console.error('[Main] 读取存储路径失败:', error)
  }
  return ''
})

ipcMain.handle('storage:setPath', (_, storagePath: string) => {
  const configPath = path.join(app.getPath('userData'), 'storage-path.json')
  const normalized = validateStoragePath(storagePath)
  fs.writeFileSync(configPath, JSON.stringify({ path: normalized }), 'utf-8')
})

function isPathAllowed(targetPath: string): boolean {
  const allowedDirs = [
    getSystemDataPath(),
    getBackendStoragePath()
  ]
  const resolved = path.resolve(targetPath)
  return allowedDirs.some(allowed => resolved.startsWith(path.resolve(allowed) + path.sep) || resolved === path.resolve(allowed))
}

ipcMain.handle('fs:readDirectory', (_, dirPath: string) => {
  if (!isPathAllowed(dirPath)) return []
  const SYSTEM_FOLDERS = ['backups', 'qdrant_storage', 'temp', '__pycache__', '.git', '.vscode', 'node_modules']
  const SYSTEM_FILES = ['storage_config.json', 'memory.db', 'memory.db-shm', 'memory.db-wal', 'embeddings.pkl', 'embedding_index.pkl']
  try {
    if (!fs.existsSync(dirPath)) return []
    const entries = fs.readdirSync(dirPath, { withFileTypes: true })
    return entries
      .filter(entry => {
        if (entry.name.startsWith('.') || entry.name === '.diamond') return false
        if (entry.isDirectory() && SYSTEM_FOLDERS.includes(entry.name)) return false
        if (entry.isFile() && SYSTEM_FILES.includes(entry.name)) return false
        return true
      })
      .map(entry => {
        const fullPath = path.join(dirPath, entry.name)
        const stat = fs.statSync(fullPath)
        return {
          name: entry.name,
          path: fullPath,
          isDirectory: entry.isDirectory(),
          extension: entry.isFile() ? path.extname(entry.name).toLowerCase() : undefined,
          size: entry.isFile() ? stat.size : undefined,
          modifiedAt: stat.mtime.toISOString(),
          isHidden: false
        }
      })
      .sort((a, b) => {
        if (a.isDirectory && !b.isDirectory) return -1
        if (!a.isDirectory && b.isDirectory) return 1
        return a.name.localeCompare(b.name)
      })
  } catch {
    return []
  }
})

ipcMain.handle('fs:readDirectoryPaged', (_, dirPath: string, options?: { offset?: number; limit?: number }) => {
  if (!isPathAllowed(dirPath)) return { entries: [], hasMore: false, nextOffset: null, total: 0 }
  const SYSTEM_FOLDERS = ['backups', 'qdrant_storage', 'temp', '__pycache__', '.git', '.vscode', 'node_modules']
  const SYSTEM_FILES = ['storage_config.json', 'memory.db', 'memory.db-shm', 'memory.db-wal', 'embeddings.pkl', 'embedding_index.pkl']
  const offset = Math.max(0, Number(options?.offset ?? 0))
  const limit = Math.min(5000, Math.max(1, Number(options?.limit ?? 300)))
  try {
    if (!fs.existsSync(dirPath)) return { entries: [], hasMore: false, nextOffset: null, total: 0 }
    const dirents = fs.readdirSync(dirPath, { withFileTypes: true })
    const filtered = dirents
      .filter(entry => {
        if (entry.name.startsWith('.') || entry.name === '.diamond') return false
        if (entry.isDirectory() && SYSTEM_FOLDERS.includes(entry.name)) return false
        if (entry.isFile() && SYSTEM_FILES.includes(entry.name)) return false
        return true
      })
      .map(entry => {
        const fullPath = path.join(dirPath, entry.name)
        return {
          name: entry.name,
          path: fullPath,
          isDirectory: entry.isDirectory(),
          extension: entry.isFile() ? path.extname(entry.name).toLowerCase() : undefined,
          isHidden: false
        }
      })
      .sort((a, b) => {
        if (a.isDirectory && !b.isDirectory) return -1
        if (!a.isDirectory && b.isDirectory) return 1
        return a.name.localeCompare(b.name, 'zh-CN')
      })

    const total = filtered.length
    const page = filtered.slice(offset, offset + limit)
    const nextOffset = offset + page.length
    const hasMore = nextOffset < total

    return { entries: page, hasMore, nextOffset: hasMore ? nextOffset : null, total }
  } catch {
    return { entries: [], hasMore: false, nextOffset: null, total: 0 }
  }
})

ipcMain.handle('fs:readFileContent', (_, filePath: string) => {
  if (!isPathAllowed(filePath)) return '[访问被拒绝：路径不在允许范围内]'
  try {
    const ext = path.extname(filePath).toLowerCase()
    const textExtensions = ['.md', '.txt', '.json', '.yaml', '.yml', '.csv', '.xml', '.html', '.css', '.js', '.ts', '.py', '.java', '.c', '.cpp', '.h', '.sh', '.bash', '.zsh', '.toml', '.ini', '.cfg', '.conf', '.log', '.env', '.sql']
    if (!textExtensions.includes(ext) && ext !== '') {
      return `[二进制文件，无法预览] ${path.basename(filePath)}`
    }
    const content = fs.readFileSync(filePath, 'utf-8')
    return content
  } catch (error: any) {
    return `[读取失败] ${error.message}`
  }
})

ipcMain.handle('project:backup', () => {
  return (async () => {
    try {
      const projectRoot = path.join(__dirname, '..', '..', '..')
      const projectBackupDir = path.join(projectRoot, '项目备份')
      const desktopFallback = path.join(app.getPath('home'), 'Desktop', '钻石记忆系统')

      // 优先使用项目内备份目录（符合项目规则）；不存在则回退到桌面（兼容已发布版本/用户习惯）
      let backupBase = projectBackupDir
      try {
        fs.mkdirSync(backupBase, { recursive: true })
      } catch {
        backupBase = desktopFallback
        fs.mkdirSync(backupBase, { recursive: true })
      }

      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      const archiveName = `Project-backup-${timestamp}.zip`
      const archivePath = path.join(backupBase, archiveName)

      const hasFrontend = fs.existsSync(path.join(projectRoot, 'frontend'))
      const hasBackend = fs.existsSync(path.join(projectRoot, 'backend'))
      if (!hasFrontend && !hasBackend) {
        return { success: false, error: '未找到项目源码目录（frontend/backend），无法备份' }
      }

      // 排除可再生目录，避免备份体积爆炸
      const excludes = [
        'node_modules/*', '.git/*', 'dist/*', '__pycache__/*', '.nuitka/*', '*.pyc', '.DS_Store',
        'frontend/node_modules/*', 'frontend/dist/*', 'backend/venv/*', 'backend/__pycache__/*'
      ]

      if (process.platform === 'win32') {
        // Windows: PowerShell Compress-Archive（系统自带，无需依赖 zip 命令）
        const psScript = [
          `$ErrorActionPreference = 'Stop'`,
          `if (Test-Path '${archivePath.replace(/'/g, "''")}') { Remove-Item -Force '${archivePath.replace(/'/g, "''")}' }`,
          `Compress-Archive -Path 'frontend','backend' -DestinationPath '${archivePath.replace(/'/g, "''")}' -Force`
        ].join('; ')
        const { code, stderr } = await spawnWithTimeout(
          'powershell',
          ['-NoProfile', '-NonInteractive', '-Command', psScript],
          { cwd: projectRoot, stdio: 'pipe' },
          5 * 60_000
        )
        if (code !== 0) return { success: false, error: stderr || `备份失败，退出码: ${code}` }
      } else {
        // macOS/Linux: zip
        const { code, stderr } = await spawnWithTimeout(
          'zip',
          ['-r', archivePath, 'frontend', 'backend', ...excludes.flatMap(e => ['-x', e])],
          { cwd: projectRoot, stdio: 'pipe' },
          5 * 60_000
        )
        if (code !== 0) return { success: false, error: stderr || `备份失败，退出码: ${code}` }
      }

      // 最多保留 10 个备份（超出清理最旧）
      const versionFiles = fs
        .readdirSync(backupBase)
        .filter(f => f.startsWith('Project-backup-') && f.endsWith('.zip'))
        .sort()
      while (versionFiles.length > 10) {
        const oldest = versionFiles.shift()!
        fs.rmSync(path.join(backupBase, oldest), { force: true })
      }

      return { success: true, path: archivePath }
    } catch (error: any) {
      return { success: false, error: error.message }
    }
  })()
})

ipcMain.handle('userData:backup', (_, backupPath: string, storagePath: string) => {
  try {
    const dataDir = storagePath || path.join(app.getPath('userData'), 'backend-data')
    if (!fs.existsSync(dataDir)) {
      return { success: false, error: '存储目录不存在' }
    }
    const backupBase = backupPath || path.join(app.getPath('home'), 'Desktop', '钻石记忆系统')
    fs.mkdirSync(backupBase, { recursive: true })
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const archiveName = `DiamondMemory-userdata-${timestamp}.zip`
    const archivePath = path.join(backupBase, archiveName)

    const excludes = ['node_modules/*', '.git/*', '__pycache__/*', '*.pyc', '.DS_Store', 'qdrant_storage/*']

    const zipProcess = spawn('zip', ['-r', archivePath, '.', ...excludes.flatMap(e => ['-x', e])], {
      cwd: dataDir, stdio: 'pipe'
    })

    return new Promise((resolve) => {
      let errorMsg = ''
      zipProcess.stderr?.on('data', (d: Buffer) => { errorMsg += d.toString() })
      zipProcess.on('exit', (code) => {
        if (code !== 0 && !fs.existsSync(archivePath)) {
          resolve({ success: false, error: `打包失败: ${errorMsg || '未知错误'}` })
          return
        }
        const versionFiles = fs.readdirSync(backupBase).filter(f => f.startsWith('DiamondMemory-userdata-') && f.endsWith('.zip')).sort()
        while (versionFiles.length > 10) {
          const oldest = versionFiles.shift()!
          fs.rmSync(path.join(backupBase, oldest), { force: true })
        }
        resolve({ success: true, path: archivePath })
      })
      zipProcess.on('error', (err) => {
        resolve({ success: false, error: err.message })
      })
    })
  } catch (error: any) {
    return { success: false, error: error.message }
  }
})

ipcMain.handle('storage:initDir', (_, dirPath: string) => {
  try {
    fs.mkdirSync(dirPath, { recursive: true })
    const userDirs = [
      path.join(dirPath, '总结经验'),
      path.join(dirPath, '技能'),
      path.join(dirPath, '用户文档')
    ]
    for (const dir of userDirs) {
      fs.mkdirSync(dir, { recursive: true })
    }
    return true
  } catch {
    return false
  }
})

ipcMain.handle('model:delete', async (_, modelName: string) => {
  try {
    const ok = await confirmDangerousAction({
      title: '确认删除模型',
      message: `确定要删除模型 "${modelName}" 吗？`,
      detail: '删除后需要重新下载才能使用。',
      confirmText: '删除'
    })
    if (!ok) return { success: false, error: '用户已取消' }

    const ollamaPath = getOllamaPath()
    const hasEmbedded = fs.existsSync(ollamaPath)
    const ollamaExe = hasEmbedded ? ollamaPath : 'ollama'
    const modelDir = getOllamaModelDir()
    const env: Record<string, string> = { ...process.env as Record<string, string> }
    if (hasEmbedded) { env.OLLAMA_MODELS = modelDir; env.OLLAMA_HOST = '127.0.0.1:11434' }
    return new Promise((resolve) => {
      const proc = spawn(ollamaExe, ['rm', modelName], { cwd: path.dirname(ollamaExe), stdio: 'pipe', detached: false, env })
      let output = ''
      proc.stdout?.on('data', (d: Buffer) => { output += d.toString() })
      proc.stderr?.on('data', (d: Buffer) => { output += d.toString() })
      proc.on('exit', (code) => {
        if (code === 0) resolve({ success: true })
        else resolve({ success: false, error: output.trim() || '删除失败' })
      })
      proc.on('error', (err) => resolve({ success: false, error: err.message }))
    })
  } catch (error: any) {
    return { success: false, error: error.message }
  }
})

ipcMain.handle('ollama:downloadProgress', () => {
  return backendManager.getOllamaDownloadProgress()
})

ipcMain.handle('ollama:isInstalled', () => {
  const ollamaPath = getOllamaPath()
  return fs.existsSync(ollamaPath)
})

function getOllamaPath(): string {
  const isDev = !app.isPackaged
  let basePath: string
  if (isDev) {
    basePath = path.resolve(__dirname, '../../../build/ollama')
  } else {
    basePath = path.join(process.resourcesPath, 'ollama')
  }
  if (process.platform === 'win32') {
    const embeddedPath = path.join(basePath, 'ollama.exe')
    if (fs.existsSync(embeddedPath)) return embeddedPath
  } else {
    const embeddedPath = path.join(basePath, 'ollama')
    if (fs.existsSync(embeddedPath)) return embeddedPath
  }
  const autoDownloadDir = path.join(app.getPath('userData'), 'ollama')
  const autoDownloadPath = process.platform === 'win32' ? path.join(autoDownloadDir, 'ollama.exe') : path.join(autoDownloadDir, 'ollama')
  if (fs.existsSync(autoDownloadPath)) return autoDownloadPath
  return autoDownloadPath
}

function getOllamaModelDir(): string {
  return path.join(app.getPath('userData'), 'ollama-models')
}

ipcMain.handle('app:getStorageInfo', () => {
  return backendManager.getStorageInfo()
})

ipcMain.handle('app:uninstall', async (_, keepData?: boolean) => {
  try {
    const ok = await confirmDangerousAction({
      title: keepData ? '确认卸载应用' : '确认卸载/清理数据',
      message: keepData
        ? '此操作将退出并卸载应用，数据文件夹将保留。'
        : '此操作将删除应用的所有本地数据（包括记忆库、知识库索引、模型配置等）。',
      detail: keepData
        ? '数据目录保留，重新安装后可继续使用。'
        : '强烈建议先执行"备份用户数据"。是否继续？',
      confirmText: keepData ? '卸载应用' : '继续删除'
    })
    if (!ok) return { success: false, error: '用户已取消' }

    isUninstalling = true

    await backendManager.gracefulShutdown()

    if (keepData) {
      await new Promise(resolve => setTimeout(resolve, 500))
      setTimeout(() => {
        isQuitting = true
        app.exit(0)
      }, 800)
      return { success: true, details: [] }
    }

    const userDataPath = app.getPath('userData')
    const legacyPaths = [
      path.join(require('os').homedir(), '.diamond-memory'),
      path.join(require('os').homedir(), 'Library', 'DiamondMemory'),
    ]

    const results: { path: string; success: boolean; error?: string }[] = []

    function removeDirWithRetry(dirPath: string, maxRetries = 3, delayMs = 1000) {
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
          if (fs.existsSync(dirPath)) {
            fs.rmSync(dirPath, { recursive: true, force: true })
            results.push({ path: dirPath, success: true })
            return
          }
          return
        } catch (e: any) {
          if (attempt === maxRetries) {
            results.push({ path: dirPath, success: false, error: e.message })
          } else {
            const syncWaitMs = delayMs * attempt
            const end = Date.now() + syncWaitMs
            while (Date.now() < end) {}
          }
        }
      }
    }

    for (const legacyPath of legacyPaths) {
      removeDirWithRetry(legacyPath)
    }

    const allLegacySuccess = results.every(r => r.success)
    const hasUserData = fs.existsSync(userDataPath)

    if (hasUserData) {
      const osTmpDir = require('os').tmpdir()
      if (process.platform === 'win32') {
        const cleanupScriptPath = path.join(osTmpDir, `dm-cleanup-${Date.now()}.bat`)
        const scriptContent = [
          '@echo off',
          'echo [DM Cleanup] 等待应用退出...',
          'ping 127.0.0.1 -n 4 > nul',
          `echo [DM Cleanup] 删除数据目录: ${userDataPath}`,
          `rd /s /q "${userDataPath}"`,
          'if %errorlevel% equ 0 (',
          '  echo [DM Cleanup] 数据目录已成功删除',
          ') else (',
          '  echo [DM Cleanup] 数据目录删除失败，5秒后重试...',
          '  ping 127.0.0.1 -n 6 > nul',
          `  rd /s /q "${userDataPath}"`,
          '  if %errorlevel% equ 0 (',
          '    echo [DM Cleanup] 重试成功，数据目录已删除',
          '  ) else (',
          '    echo [DM Cleanup] 重试仍失败，请手动删除: ' + userDataPath,
          '  )',
          ')',
          `del /f /q "${cleanupScriptPath}"`,
          'echo [DM Cleanup] 清理脚本执行完毕',
        ].join('\r\n')
        fs.writeFileSync(cleanupScriptPath, scriptContent)

        spawn('cmd.exe', ['/c', cleanupScriptPath], {
          detached: true,
          stdio: 'ignore',
        }).unref()
      } else {
        const cleanupScriptPath = path.join(osTmpDir, `dm-cleanup-${Date.now()}.sh`)
        const scriptContent = [
          '#!/bin/bash',
          'echo "[DM Cleanup] 等待应用退出..."',
          'sleep 3',
          `echo "[DM Cleanup] 删除数据目录: ${userDataPath}"`,
          `rm -rf "${userDataPath}"`,
          'if [ $? -eq 0 ]; then',
          '  echo "[DM Cleanup] 数据目录已成功删除"',
          'else',
          '  echo "[DM Cleanup] 数据目录删除失败，5秒后重试..."',
          '  sleep 5',
          `  rm -rf "${userDataPath}"`,
          '  if [ $? -eq 0 ]; then',
          '    echo "[DM Cleanup] 重试成功，数据目录已删除"',
          '  else',
          '    echo "[DM Cleanup] 重试仍失败，请手动删除: ' + userDataPath + '"',
          '  fi',
          'fi',
          `rm -f "${cleanupScriptPath}"`,
          'echo "[DM Cleanup] 清理脚本执行完毕"',
        ].join('\n')
        fs.writeFileSync(cleanupScriptPath, scriptContent, { mode: 0o755 })

        spawn('/bin/bash', [cleanupScriptPath], {
          detached: true,
          stdio: 'ignore',
        }).unref()
      }

      results.push({ path: userDataPath, success: true })
    }

    const allSuccess = results.every(r => r.success)

    await new Promise(resolve => setTimeout(resolve, 500))

    setTimeout(() => {
      isQuitting = true
      app.exit(0)
    }, 800)

    return { success: allSuccess && allLegacySuccess, details: results }
  } catch (error: any) {
    return { success: false, error: error.message }
  }
})

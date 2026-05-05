export interface IElectronAPI {
  getBackendStatus: () => Promise<{
    isRunning: boolean
    state: 'idle' | 'starting' | 'running' | 'error'
    port: number
    lastError: string
  }>
  restartBackend: () => Promise<boolean>
  stopBackend: () => Promise<boolean>
  getAppInfo: () => Promise<{ platform: string; version: string; isPackaged: boolean }>
  getAppRunId: () => Promise<string>
  isFirstRun: () => Promise<boolean>
  relaunchApp: () => Promise<boolean>

  // 生产环境请求代理（绕开 CORS）：IPC → 主进程 → HTTP(127.0.0.1)
  httpRequest: (payload: {
    method: string
    path: string
    headers?: Record<string, string>
    bodyType?: 'json' | 'text' | 'binary'
    body?: any
    timeoutMs?: number
  }) => Promise<{
    ok: boolean
    status: number
    headers: Record<string, string>
    dataType: 'json' | 'text' | 'binary'
    data: any
    error?: string
  }>

  httpStreamStart: (payload: {
    method: string
    path: string
    headers?: Record<string, string>
    bodyType?: 'json' | 'text' | 'binary'
    body?: any
  }) => Promise<{ ok: boolean; streamId: string; error?: string }>

  httpStreamAbort: (streamId: string) => Promise<boolean>

  onHttpStreamChunk: (callback: (payload: { streamId: string; chunk: string }) => void) => () => void
  onHttpStreamDone: (callback: (payload: { streamId: string }) => void) => () => void
  onHttpStreamError: (callback: (payload: { streamId: string; error: string }) => void) => () => void

  httpUploadFile: (payload: { filename: string; mime: string; buffer: ArrayBuffer; disturbFree?: boolean }) => Promise<{
    ok: boolean
    status: number
    data: string
    error?: string
  }>

  httpCrawlUrl: (url: string) => Promise<{ ok: boolean; status: number; data: string; error?: string }>

  selectDirectory: (options?: { title?: string }) => Promise<string | null>
  getStoragePath: () => Promise<string>
  setStoragePath: (path: string) => Promise<void>
  readDirectory: (dirPath: string) => Promise<FileEntry[]>
  readDirectoryPaged: (
    dirPath: string,
    options?: { offset?: number; limit?: number }
  ) => Promise<{ entries: FileEntry[]; hasMore: boolean; nextOffset: number | null; total: number }>
  readFileContent: (filePath: string) => Promise<string>
  backupProject: () => Promise<{ success: boolean; path?: string; error?: string }>
  backupUserData: (backupPath: string, storagePath: string) => Promise<{ success: boolean; path?: string; error?: string }>
  initStorageDir: (dirPath: string) => Promise<boolean>
  deleteModel: (modelName: string) => Promise<{ success: boolean; error?: string }>
  getOllamaDownloadProgress: () => Promise<{ status: string; progress: number; downloaded: number; total: number }>
  isOllamaInstalled: () => Promise<boolean>
  minimizeWindow: () => Promise<void>
  maximizeWindow: () => Promise<void>
  closeWindow: () => Promise<void>
  toggleMaximize: () => Promise<void>
  checkForUpdates: () => Promise<{ available: boolean; info: any }>
  downloadUpdate: () => Promise<boolean>
  installUpdate: () => Promise<boolean>
  onUpdateAvailable: (callback: (info: UpdateInfo) => void) => () => void
  onUpdateNotAvailable: (callback: (info: any) => void) => () => void
  onUpdateError: (callback: (info: any) => void) => () => void
  onUpdateDownloadProgress: (callback: (info: DownloadProgress) => void) => () => void
  onUpdateDownloaded: (callback: (info: UpdateInfo) => void) => () => void
  getStorageInfo: () => Promise<{ userDataPath: string; ollamaPath: string; ollamaModelPath: string; backendDataPath: string }>
  uninstallApp: (keepData?: boolean) => Promise<{ success: boolean; details?: Array<{ path: string; success: boolean; error?: string }>; error?: string }>
}

export interface UpdateInfo {
  version: string
  releaseDate: string
  releaseNotes: string
}

export interface DownloadProgress {
  percent: number
  speed: string
  transferred: string
  total: string
}

export interface FileEntry {
  name: string
  path: string
  isDirectory: boolean
  extension?: string
  size?: number
  modifiedAt?: string
  isHidden?: boolean
}

declare global {
  interface Window {
    electronAPI: IElectronAPI
  }
}

export {}

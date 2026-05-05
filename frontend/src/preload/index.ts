const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendStatus: () => ipcRenderer.invoke('backend:status'),
  restartBackend: () => ipcRenderer.invoke('backend:restart'),
  stopBackend: () => ipcRenderer.invoke('backend:stop'),
  getAppInfo: () => ipcRenderer.invoke('app:info'),
  getAppRunId: () => ipcRenderer.invoke('app:runId'),
  isFirstRun: () => ipcRenderer.invoke('app:isFirstRun'),
  relaunchApp: () => ipcRenderer.invoke('app:relaunch'),
  // 生产环境请求代理（绕开 CORS）：IPC → 主进程 → HTTP(127.0.0.1)
  httpRequest: (payload: any) => ipcRenderer.invoke('http:request', payload),
  httpStreamStart: (payload: any) => ipcRenderer.invoke('http:stream:start', payload),
  httpStreamAbort: (streamId: string) => ipcRenderer.invoke('http:stream:abort', streamId),
  httpUploadFile: (payload: any) => ipcRenderer.invoke('http:upload:file', payload),
  httpCrawlUrl: (url: string) => ipcRenderer.invoke('http:crawl:url', url),
  onHttpStreamChunk: (callback: (payload: any) => void) => {
    const handler = (_event: any, payload: any) => callback(payload)
    ipcRenderer.on('http:stream:chunk', handler)
    return () => ipcRenderer.removeListener('http:stream:chunk', handler)
  },
  onHttpStreamDone: (callback: (payload: any) => void) => {
    const handler = (_event: any, payload: any) => callback(payload)
    ipcRenderer.on('http:stream:done', handler)
    return () => ipcRenderer.removeListener('http:stream:done', handler)
  },
  onHttpStreamError: (callback: (payload: any) => void) => {
    const handler = (_event: any, payload: any) => callback(payload)
    ipcRenderer.on('http:stream:error', handler)
    return () => ipcRenderer.removeListener('http:stream:error', handler)
  },
  selectDirectory: (options?: { title?: string }) => ipcRenderer.invoke('dialog:selectDirectory', options),
  getStoragePath: () => ipcRenderer.invoke('storage:getPath'),
  setStoragePath: (path: string) => ipcRenderer.invoke('storage:setPath', path),
  readDirectory: (dirPath: string) => ipcRenderer.invoke('fs:readDirectory', dirPath),
  readDirectoryPaged: (dirPath: string, options?: { offset?: number; limit?: number }) =>
    ipcRenderer.invoke('fs:readDirectoryPaged', dirPath, options),
  readFileContent: (filePath: string) => ipcRenderer.invoke('fs:readFileContent', filePath),
  backupProject: () => ipcRenderer.invoke('project:backup'),
  backupUserData: (backupPath: string, storagePath: string) => ipcRenderer.invoke('userData:backup', backupPath, storagePath),
  initStorageDir: (dirPath: string) => ipcRenderer.invoke('storage:initDir', dirPath),
  deleteModel: (modelName: string) => ipcRenderer.invoke('model:delete', modelName),
  getOllamaDownloadProgress: () => ipcRenderer.invoke('ollama:downloadProgress'),
  isOllamaInstalled: () => ipcRenderer.invoke('ollama:isInstalled'),
  minimizeWindow: () => ipcRenderer.invoke('window:minimize'),
  maximizeWindow: () => ipcRenderer.invoke('window:maximize'),
  closeWindow: () => ipcRenderer.invoke('window:close'),
  toggleMaximize: () => ipcRenderer.invoke('window:toggleMaximize'),
  checkForUpdates: () => ipcRenderer.invoke('update:check'),
  downloadUpdate: () => ipcRenderer.invoke('update:download'),
  installUpdate: () => ipcRenderer.invoke('update:install'),
  onUpdateAvailable: (callback: (info: any) => void) => {
    const handler = (_event: any, info: any) => callback(info)
    ipcRenderer.on('update:available', handler)
    return () => ipcRenderer.removeListener('update:available', handler)
  },
  onUpdateNotAvailable: (callback: (info: any) => void) => {
    const handler = (_event: any, info: any) => callback(info)
    ipcRenderer.on('update:not-available', handler)
    return () => ipcRenderer.removeListener('update:not-available', handler)
  },
  onUpdateError: (callback: (info: any) => void) => {
    const handler = (_event: any, info: any) => callback(info)
    ipcRenderer.on('update:error', handler)
    return () => ipcRenderer.removeListener('update:error', handler)
  },
  onUpdateDownloadProgress: (callback: (info: any) => void) => {
    const handler = (_event: any, info: any) => callback(info)
    ipcRenderer.on('update:download-progress', handler)
    return () => ipcRenderer.removeListener('update:download-progress', handler)
  },
  onUpdateDownloaded: (callback: (info: any) => void) => {
    const handler = (_event: any, info: any) => callback(info)
    ipcRenderer.on('update:downloaded', handler)
    return () => ipcRenderer.removeListener('update:downloaded', handler)
  },
  getStorageInfo: () => ipcRenderer.invoke('app:getStorageInfo'),
  uninstallApp: (keepData?: boolean) => ipcRenderer.invoke('app:uninstall', keepData)
})

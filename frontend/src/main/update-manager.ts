import pkg from 'electron-updater'
const { autoUpdater } = pkg
import { BrowserWindow, ipcMain, dialog } from 'electron'

export class UpdateManager {
  private mainWindow: BrowserWindow | null = null
  private updateAvailable = false
  private updateInfo: any = null
  private autoCheckEnabled = true

  initialize(mainWindow: BrowserWindow) {
    this.mainWindow = mainWindow

    autoUpdater.autoDownload = false
    autoUpdater.autoInstallOnAppQuit = true

    autoUpdater.on('checking-for-update', () => {
      console.log('[Update] 正在检查更新...')
      this.sendToRenderer('update:checking', { message: '正在检查更新...' })
    })

    autoUpdater.on('update-available', (info) => {
      console.log('[Update] 发现新版本:', info.version)
      this.updateAvailable = true
      this.updateInfo = info
      this.sendToRenderer('update:available', {
        version: info.version,
        releaseDate: info.releaseDate,
        releaseNotes: info.releaseNotes || '暂无更新说明'
      })
    })

    autoUpdater.on('update-not-available', (info) => {
      console.log('[Update] 已是最新版本:', info.version)
      this.updateAvailable = false
      this.sendToRenderer('update:not-available', {
        version: info.version,
        message: '当前已是最新版本'
      })
    })

    autoUpdater.on('error', (err) => {
      console.error('[Update] 更新检查失败:', err)
      this.sendToRenderer('update:error', {
        message: `检查更新失败: ${err.message}`
      })
    })

    autoUpdater.on('download-progress', (progressObj) => {
      const percent = Math.round(progressObj.percent)
      const speed = (progressObj.bytesPerSecond / 1024 / 1024).toFixed(2)
      const transferred = (progressObj.transferred / 1024 / 1024).toFixed(2)
      const total = (progressObj.total / 1024 / 1024).toFixed(2)
      
      this.sendToRenderer('update:download-progress', {
        percent,
        speed: `${speed} MB/s`,
        transferred: `${transferred} MB`,
        total: `${total} MB`
      })
    })

    autoUpdater.on('update-downloaded', (info) => {
      console.log('[Update] 更新包下载完成:', info.version)
      this.sendToRenderer('update:downloaded', {
        version: info.version,
        releaseNotes: info.releaseNotes || '暂无更新说明'
      })

      dialog.showMessageBox(this.mainWindow!, {
        type: 'info',
        title: '更新已就绪',
        message: `新版本 ${info.version} 已下载完成`,
        detail: '应用将在重启后安装更新',
        buttons: ['稍后重启', '立即重启'],
        cancelId: 0,
        defaultId: 1
      }).then(result => {
        if (result.response === 1) {
          autoUpdater.quitAndInstall(false, true)
        }
      })
    })

    this.setupIpcHandlers()

    if (this.autoCheckEnabled) {
      setTimeout(() => {
        this.checkForUpdates()
      }, 3000)
    }
  }

  private setupIpcHandlers() {
    ipcMain.handle('update:check', async () => {
      await this.checkForUpdates()
      return {
        available: this.updateAvailable,
        info: this.updateInfo
      }
    })

    ipcMain.handle('update:download', async () => {
      if (this.updateAvailable) {
        await autoUpdater.downloadUpdate()
        return true
      }
      return false
    })

    ipcMain.handle('update:install', async () => {
      autoUpdater.quitAndInstall(false, true)
      return true
    })
  }

  async checkForUpdates() {
    try {
      await autoUpdater.checkForUpdates()
    } catch (error: any) {
      console.error('[Update] 检查更新异常:', error)
    }
  }

  private sendToRenderer(channel: string, data: any) {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send(channel, data)
    }
  }
}

export const updateManager = new UpdateManager()

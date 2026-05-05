import path from 'path'

/**
 * 判断是否应将旧版（userData/backend-data）中的系统数据迁移到“工作区数据目录”。
 *
 * 规则：
 * - 仅当旧数据目录的 storage_config.json 声明的 storage_path 与当前 configuredStoragePath 一致时才迁移
 * - 避免用户切换到一个全新空工作区时被“自动带入旧数据”
 */
export function shouldMigrateLegacySystemData(options: {
  legacyStoragePath?: string | null
  configuredStoragePath?: string | null
}): boolean {
  const legacy = (options.legacyStoragePath || '').trim()
  const configured = (options.configuredStoragePath || '').trim()
  if (!legacy || !configured) return false
  try {
    return path.resolve(legacy) === path.resolve(configured)
  } catch {
    return false
  }
}


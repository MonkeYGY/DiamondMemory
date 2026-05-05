import path from 'path'

/**
 * 后端运行时写入根目录（必须为 Electron userData 下目录）
 * - 约束：安装目录只读，不允许后端写入 resourcesPath / projectRoot
 */
export function resolveSystemDataPath(userDataPath: string): string {
  return path.join(userDataPath, 'backend-data')
}

/**
 * 用户可变更的存储路径（知识库/用户文档等）
 * - 未配置时回退到 systemDataPath
 */
export function resolveStoragePath(systemDataPath: string, configuredStoragePath?: string | null): string {
  if (configuredStoragePath && configuredStoragePath.trim()) return configuredStoragePath
  return systemDataPath
}

export function resolveBackendPaths(
  userDataPath: string,
  configuredStoragePath?: string | null
): { systemDataPath: string; storagePath: string } {
  const defaultSystemDataPath = resolveSystemDataPath(userDataPath)
  const storagePath = resolveStoragePath(defaultSystemDataPath, configuredStoragePath)

  // 工作区隔离：
  // - 未配置 storagePath：沿用旧逻辑（userData/backend-data），保证兼容
  // - 配置了 storagePath：将系统数据（db/索引/qdrant/temp/backups/config）落到
  //   storagePath/.diamond/backend-data，避免“切换工作区后仍命中旧数据库”的体验问题
  if (storagePath !== defaultSystemDataPath) {
    return {
      systemDataPath: path.join(storagePath, '.diamond', 'backend-data'),
      storagePath
    }
  }

  return { systemDataPath: defaultSystemDataPath, storagePath }
}

/**
 * 路径工具：用于存储路径切换时做“是否仍在工作区内”的判断
 *
 * 注意：
 * - 该文件运行在 renderer（浏览器环境）中，不依赖 Node.js 的 path 模块
 * - 仅用于“绝对路径前缀 + 边界”判断，不做真实的文件系统解析
 */

function normalizeForCompare(p: string): { norm: string; caseInsensitive: boolean } {
  const raw = (p || '').trim().replace(/\\/g, '/')
  const isWindowsPath = /^[a-zA-Z]:\//.test(raw)

  // 去掉末尾多余 /
  const norm = raw.replace(/\/+$/g, '')
  return {
    norm: isWindowsPath ? norm.toLowerCase() : norm,
    caseInsensitive: isWindowsPath,
  }
}

/**
 * 判断 targetPath 是否位于 rootPath 下（包含 rootPath 本身）。
 *
 * - 支持 Windows `C:\foo\bar` 与 POSIX `/foo/bar`（仅做字符串规范化）
 * - 会进行“边界”判断，避免 `/a/foo` 误匹配 `/a/foobar`
 */
export function isPathWithinRoot(targetPath: string, rootPath: string): boolean {
  const t = normalizeForCompare(targetPath)
  const r = normalizeForCompare(rootPath)

  if (!t.norm || !r.norm) return false

  if (t.norm === r.norm) return true
  return t.norm.startsWith(r.norm + '/')
}

/**
 * 存储路径切换后，如果当前选中的文件不再属于新工作区，应该清空选中态，
 * 否则会触发 IPC “访问被拒绝：路径不在允许范围内”。
 */
export function shouldClearSelectedFile(selectedFilePath: string | null | undefined, newStorageRoot: string): boolean {
  if (!selectedFilePath) return false
  if (!newStorageRoot) return true
  return !isPathWithinRoot(selectedFilePath, newStorageRoot)
}


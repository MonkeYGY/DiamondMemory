import { describe, expect, it } from 'vitest'
import { isPathWithinRoot, shouldClearSelectedFile } from './path-utils'

describe('path-utils', () => {
  it('isPathWithinRoot：应支持 POSIX 边界判断', () => {
    expect(isPathWithinRoot('/a/work', '/a/work')).toBe(true)
    expect(isPathWithinRoot('/a/work/用户文档/a.md', '/a/work')).toBe(true)
    expect(isPathWithinRoot('/a/workspace-x/a.md', '/a/work')).toBe(false)
  })

  it('isPathWithinRoot：应支持 Windows 路径（大小写不敏感 + 反斜杠）', () => {
    expect(isPathWithinRoot('C:\\Work', 'c:\\work')).toBe(true)
    expect(isPathWithinRoot('C:\\Work\\Docs\\a.md', 'c:\\work')).toBe(true)
    expect(isPathWithinRoot('C:\\WorkspaceX\\a.md', 'c:\\work')).toBe(false)
  })

  it('shouldClearSelectedFile：切换工作区后应清空旧选中文件', () => {
    expect(shouldClearSelectedFile('/old/root/a.md', '/new/root')).toBe(true)
    expect(shouldClearSelectedFile('/new/root/a.md', '/new/root')).toBe(false)
    expect(shouldClearSelectedFile(null, '/new/root')).toBe(false)
  })
})


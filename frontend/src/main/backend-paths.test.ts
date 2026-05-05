import { describe, expect, it } from 'vitest'
import { resolveBackendPaths } from './backend-paths'

describe('resolveBackendPaths（工作区隔离）', () => {
  it('配置了 storagePath 时：systemDataPath 应落到 storagePath/.diamond/backend-data', () => {
    const userDataPath = '/Users/alice/Library/Application Support/DiamondMemory'
    const configuredStoragePath = '/Volumes/BigDisk/知识库'

    const { systemDataPath, storagePath } = resolveBackendPaths(userDataPath, configuredStoragePath)

    expect(storagePath).toBe(configuredStoragePath)
    expect(systemDataPath).toBe('/Volumes/BigDisk/知识库/.diamond/backend-data')
  })

  it('未配置 storagePath 时：systemDataPath/storagePath 均回退到 userData/backend-data', () => {
    const userDataPath = '/Users/alice/Library/Application Support/DiamondMemory'

    const { systemDataPath, storagePath } = resolveBackendPaths(userDataPath, '')

    expect(systemDataPath).toBe(`${userDataPath}/backend-data`)
    expect(storagePath).toBe(`${userDataPath}/backend-data`)
  })
})


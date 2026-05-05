import test from 'node:test'
import assert from 'node:assert/strict'

// 注意：此测试依赖 `npm -C frontend run electron:build-main` 生成 dist 产物
import { resolveBackendPaths } from '../dist/main/backend-paths.js'

test('resolveBackendPaths: 配置 storagePath 时，systemDataPath 应落到 storagePath/.diamond/backend-data', () => {
  const userDataPath = '/Users/alice/Library/Application Support/DiamondMemory'

  const { systemDataPath, storagePath } = resolveBackendPaths(userDataPath, '/Volumes/BigDisk/知识库')

  assert.equal(storagePath, '/Volumes/BigDisk/知识库')
  assert.equal(systemDataPath, '/Volumes/BigDisk/知识库/.diamond/backend-data')
})

test('resolveBackendPaths: 未配置 storagePath 时，storagePath 回退到 systemDataPath', () => {
  const userDataPath = '/Users/alice/Library/Application Support/DiamondMemory'

  const { systemDataPath, storagePath } = resolveBackendPaths(userDataPath, '')

  assert.equal(systemDataPath, `${userDataPath}/backend-data`)
  assert.equal(storagePath, `${userDataPath}/backend-data`)
})

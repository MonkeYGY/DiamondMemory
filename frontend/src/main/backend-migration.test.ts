import { describe, expect, it } from 'vitest'
import { shouldMigrateLegacySystemData } from './backend-migration'

describe('shouldMigrateLegacySystemData', () => {
  it('legacyStoragePath 与 configuredStoragePath 一致时返回 true', () => {
    expect(
      shouldMigrateLegacySystemData({
        legacyStoragePath: '/Users/a/workspace',
        configuredStoragePath: '/Users/a/workspace'
      })
    ).toBe(true)
  })

  it('legacyStoragePath 与 configuredStoragePath 不一致时返回 false', () => {
    expect(
      shouldMigrateLegacySystemData({
        legacyStoragePath: '/Users/a/old',
        configuredStoragePath: '/Users/a/new'
      })
    ).toBe(false)
  })

  it('缺少任一方时返回 false', () => {
    expect(shouldMigrateLegacySystemData({ legacyStoragePath: '', configuredStoragePath: '/x' })).toBe(false)
    expect(shouldMigrateLegacySystemData({ legacyStoragePath: '/x', configuredStoragePath: '' })).toBe(false)
  })
})


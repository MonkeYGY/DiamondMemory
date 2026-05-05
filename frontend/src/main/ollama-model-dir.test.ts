import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'fs'
import path from 'path'
import { EventEmitter } from 'events'

const paths = vi.hoisted(() => {
  const base = '/tmp/dm-ollama-test'
  return { base, home: `${base}/home`, userData: `${base}/userData` }
})

vi.mock('electron', () => {
  return {
    app: {
      isPackaged: false,
      getPath: (name: string) => {
        if (name === 'home') return paths.home
        if (name === 'userData') return paths.userData
        return paths.base
      }
    }
  }
})

vi.mock('child_process', async () => {
  const actual: any = await vi.importActual('child_process')
  return {
    ...actual,
    execSync: () => {
      throw new Error('no system ollama in test')
    }
  }
})

import { BackendManager } from './backend-manager'

class FakeChildProcess extends EventEmitter {
  stdout = new EventEmitter()
  stderr = new EventEmitter()
  kill() {}
}

class TestBackendManager extends BackendManager {
  public lastSpawnEnv: Record<string, string> | undefined
  protected spawnProcessForTest(command: string, args: string[], options: any) {
    this.lastSpawnEnv = options?.env
    return new FakeChildProcess() as any
  }
}

function makeValidModelsDir(dir: string) {
  const manifests = path.join(dir, 'manifests')
  fs.mkdirSync(manifests, { recursive: true })
  fs.writeFileSync(path.join(manifests, 'dummy'), '1', 'utf-8')
}

beforeEach(() => {
  try {
    fs.rmSync(paths.base, { recursive: true, force: true })
  } catch {}
  fs.mkdirSync(paths.home, { recursive: true })
  fs.mkdirSync(paths.userData, { recursive: true })
})

afterEach(() => {
  delete process.env.OLLAMA_MODELS
  vi.restoreAllMocks()
})

describe('Ollama 模型目录复用（OLLAMA_MODELS）', () => {
  it('优先使用 process.env.OLLAMA_MODELS（存在且有效）', async () => {
    const legacy = path.join(paths.base, 'legacy-models')
    makeValidModelsDir(legacy)
    process.env.OLLAMA_MODELS = legacy

    let calls = 0
    global.fetch = vi.fn(async () => {
      calls += 1
      return { ok: calls > 1 } as any
    }) as any

    const manager = new TestBackendManager()
    ;(manager as any).getOllamaPath = () => {
      const p = path.join(paths.base, 'ollama')
      fs.mkdirSync(path.dirname(p), { recursive: true })
      fs.writeFileSync(p, 'bin', 'utf-8')
      return p
    }

    const ok = await manager.startOllama()
    expect(ok).toBe(true)
    expect(manager.lastSpawnEnv?.OLLAMA_MODELS).toBe(legacy)
  })

  it('无旧模型时回退到 userData/ollama-models', async () => {
    let calls = 0
    global.fetch = vi.fn(async () => {
      calls += 1
      return { ok: calls > 1 } as any
    }) as any

    const manager = new TestBackendManager()
    ;(manager as any).getOllamaPath = () => {
      const p = path.join(paths.base, 'ollama')
      fs.mkdirSync(path.dirname(p), { recursive: true })
      fs.writeFileSync(p, 'bin', 'utf-8')
      return p
    }

    const ok = await manager.startOllama()
    expect(ok).toBe(true)
    expect(manager.lastSpawnEnv?.OLLAMA_MODELS).toBe(path.join(paths.userData, 'ollama-models'))
  })
})

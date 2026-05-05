import { describe, expect, it } from 'vitest'
import { buildPromptWindow } from './prompt-window'

describe('buildPromptWindow', () => {
  it('returns dropped messages when trimmed', () => {
    const all = [
      { role: 'user', content: 'a'.repeat(2000) },
      { role: 'assistant', content: 'b'.repeat(2000) },
      { role: 'user', content: 'hi' }
    ]
    const { kept, dropped, trimmed } = buildPromptWindow(all, { maxMessages: 24, tokenBudget: 200 })
    expect(trimmed).toBe(true)
    expect(kept.length).toBe(1)
    expect(kept[0].content).toBe('hi')
    expect(dropped.length).toBe(2)
  })
})


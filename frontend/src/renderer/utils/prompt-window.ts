export function estimateTokens(text: string): number {
  return Math.ceil((text || '').length * 1.2)
}

export function buildPromptWindow(
  all: Array<{ role: string; content: string }>,
  opts: { maxMessages: number; tokenBudget: number }
): { kept: Array<{ role: string; content: string }>; dropped: Array<{ role: string; content: string }>; trimmed: boolean } {
  let budget = opts.tokenBudget
  const picked: Array<{ role: string; content: string }> = []
  for (let i = all.length - 1; i >= 0; i--) {
    const m = all[i]
    const t = estimateTokens(m.content) + 16
    if (picked.length >= opts.maxMessages) break
    if (picked.length > 0 && budget - t < 0) break
    picked.push(m)
    budget -= t
    if (budget <= 0) break
  }
  const kept = picked.reverse()
  const trimmed = kept.length < all.length
  const dropped = trimmed ? all.slice(0, all.length - kept.length) : []
  return { kept, dropped, trimmed }
}


import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({
  gfm: true,
  breaks: true
})

export function normalizeMemoryDetailMarkdown(raw: string): string {
  return (raw || '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function renderMemoryDetailMarkdown(raw: string): string {
  const normalized = normalizeMemoryDetailMarkdown(raw)
  const html = marked.parse(normalized) as string
  return DOMPurify.sanitize(html)
}

export function renderKnowledgeMarkdown(raw: string): string {
  if (!raw) return ''
  let content = raw
  const frontmatterMatch = content.match(/^---\n[\s\S]*?\n---\n?/)
  if (frontmatterMatch) {
    content = content.slice(frontmatterMatch[0].length)
  }
  content = content.trim()
  const html = marked.parse(content) as string
  return DOMPurify.sanitize(html)
}

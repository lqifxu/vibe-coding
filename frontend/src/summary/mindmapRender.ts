import type { MindmapNode } from './summaryTypes'

export type MindmapRenderOpts = {
  /** Pixel scale for HD export (1 = preview, 2 = download). */
  scale?: number
  /** Prefer fuller labels (export); preview may truncate more aggressively. */
  fullText?: boolean
}

type LaidOutNode = {
  name: string
  lines: string[]
  x: number
  y: number
  depth: number
  parentX?: number
  parentY?: number
  w: number
  h: number
  color: string
  hasChildren: boolean
}

/** Markmap-like branch palette. */
const BRANCH_COLORS = [
  '#f59e0b',
  '#10b981',
  '#ec4899',
  '#3b82f6',
  '#8b5cf6',
  '#14b8a6',
  '#f43f5e',
  '#84cc16',
]

const FONT =
  '"Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif'

const ROOT_COLOR = '#334155'
const PAD_X = 44
const PAD_Y = 36
const LINE_GAP = 2
/** Horizontal gap between end of parent text and child dot */
const H_GAP = 48
const MIN_LEAF_SLOT = 40

/**
 * Normalize mindmap label for display:
 * - strip markdown markers (** __ ` *)
 * - strip timeline stamps in () （） [] 【】
 */
export function cleanMindmapLabel(text: string): string {
  let s = text || ''
  // markdown emphasis / code
  s = s.replace(/`+/g, '')
  s = s.replace(/\*\*/g, '')
  s = s.replace(/__/g, '')
  s = s.replace(/\*/g, '')
  // timestamps: (00:00) （01:10） [03:25] 【04:00】
  s = s.replace(/\s*[（(\[【]\s*\d{1,2}:\d{2}(?::\d{2})?\s*[）)\]】]\s*/g, ' ')
  // leading "00:00 - " / "00:00："
  s = s.replace(/^\s*\d{1,2}:\d{2}(?::\d{2})?\s*[-–—:：]\s*/, '')
  // orphaned brackets left from partial stamps
  s = s.replace(/\s*[\[【]\s*[\]】]\s*/g, ' ')
  s = s.replace(/\s+/g, ' ').trim()
  s = s.replace(/^[\s\-–—:：|]+|[\s\-–—:：|]+$/g, '').trim()
  return s
}

/** @deprecated use cleanMindmapLabel */
export function stripTimeline(text: string): string {
  return cleanMindmapLabel(text)
}

function sanitizeTree(node: MindmapNode): MindmapNode {
  return {
    name: cleanMindmapLabel(node.name || '') || '节点',
    children: (node.children || []).map(sanitizeTree),
  }
}

function countLeaves(node: MindmapNode): number {
  const kids = node.children || []
  if (!kids.length) return 1
  return kids.reduce((n, c) => n + countLeaves(c), 0)
}

function fontFor(depth: number): string {
  if (depth === 0) return `600 14px ${FONT}`
  if (depth === 1) return `600 13px ${FONT}`
  return `12px ${FONT}`
}

function lineHeightFor(depth: number): number {
  if (depth === 0) return 19
  if (depth === 1) return 17
  return 16
}

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
  maxLines: number,
): string[] {
  const raw = text.trim()
  if (!raw) return ['']
  if (ctx.measureText(raw).width <= maxWidth) return [raw]

  const chars = [...raw]
  const lines: string[] = []
  let cur = ''

  const pushEllipsis = (base: string) => {
    let t = base
    while (t.length > 1 && ctx.measureText(`${t}…`).width > maxWidth) t = t.slice(0, -1)
    lines.push(`${t}…`)
  }

  for (let i = 0; i < chars.length; i++) {
    const next = cur + chars[i]
    if (ctx.measureText(next).width <= maxWidth) {
      cur = next
      continue
    }
    if (lines.length >= maxLines - 1) {
      pushEllipsis(cur || chars[i])
      return lines
    }
    if (cur) lines.push(cur)
    cur = chars[i]
  }
  if (cur) {
    if (lines.length >= maxLines) {
      pushEllipsis(lines.pop() || cur)
    } else {
      lines.push(cur)
    }
  }
  return lines.length ? lines : [raw]
}

function maxLineWidth(depth: number, fullText: boolean): number {
  // Keep root compact so L1 branches sit closer (reference style)
  if (depth === 0) return fullText ? 200 : 180
  if (depth === 1) return fullText ? 160 : 140
  return fullText ? 260 : 210
}

function maxLines(depth: number, fullText: boolean): number {
  if (depth === 0) return fullText ? 4 : 3
  if (depth === 1) return 2
  return fullText ? 3 : 2
}

type Measured = {
  name: string
  lines: string[]
  w: number
  h: number
  depth: number
  color: string
  hasChildren: boolean
  children: Measured[]
  x: number
  y: number
  parentX?: number
  parentY?: number
}

function measureTree(
  node: MindmapNode,
  ctx: CanvasRenderingContext2D,
  depth: number,
  fullText: boolean,
  branchIndex: number,
  color: string,
): Measured {
  const name = cleanMindmapLabel(node.name || '') || '节点'
  ctx.font = fontFor(depth)
  const lines = wrapText(ctx, name, maxLineWidth(depth, fullText), maxLines(depth, fullText))
  const lh = lineHeightFor(depth)
  const textW = Math.max(...lines.map((l) => ctx.measureText(l).width), 20)
  const w = textW
  const h = lines.length * lh + Math.max(0, lines.length - 1) * LINE_GAP
  const kids = node.children || []
  const children = kids.map((child, i) => {
    const bi = depth === 0 ? i : branchIndex
    const childColor =
      depth === 0
        ? BRANCH_COLORS[i % BRANCH_COLORS.length]
        : BRANCH_COLORS[(bi + Math.min(i, 3)) % BRANCH_COLORS.length]
    return measureTree(child, ctx, depth + 1, fullText, bi, childColor)
  })
  return {
    name,
    lines,
    w,
    h,
    depth,
    color,
    hasChildren: children.length > 0,
    children,
    x: 0,
    y: 0,
  }
}

function subtreeLeaves(m: Measured): number {
  if (!m.children.length) return 1
  return m.children.reduce((n, c) => n + subtreeLeaves(c), 0)
}

/** Needed vertical span so multi-line nodes don't overlap. */
function minSpan(m: Measured): number {
  if (!m.children.length) return Math.max(MIN_LEAF_SLOT, m.h + 12)
  const childSum = m.children.reduce((n, c) => n + minSpan(c), 0)
  return Math.max(childSum, m.h + 16)
}

function assignPositions(m: Measured, x: number, y0: number, y1: number, parent?: Measured) {
  m.x = x
  m.y = (y0 + y1) / 2
  if (parent) {
    // Parent connector exits just after parent text
    m.parentX = parent.x + 10 + parent.w + 8
    m.parentY = parent.y
  }
  if (!m.children.length) return

  const spans = m.children.map((c) => minSpan(c))
  const totalMin = spans.reduce((a, b) => a + b, 0)
  const avail = Math.max(y1 - y0, totalMin)
  let cursor = y0
  // Child column starts after this node's text block
  const childX = x + 10 + m.w + H_GAP
  m.children.forEach((child, i) => {
    const share = (spans[i] / totalMin) * avail
    assignPositions(child, childX, cursor, cursor + share, m)
    cursor += share
  })
}

function flatten(m: Measured, out: LaidOutNode[] = []): LaidOutNode[] {
  out.push({
    name: m.name,
    lines: m.lines,
    x: m.x,
    y: m.y,
    depth: m.depth,
    parentX: m.parentX,
    parentY: m.parentY,
    w: m.w,
    h: m.h,
    color: m.color,
    hasChildren: m.hasChildren,
  })
  m.children.forEach((c) => flatten(c, out))
  return out
}

function layoutMindmap(
  root: MindmapNode,
  ctx: CanvasRenderingContext2D,
  fullText: boolean,
): { nodes: LaidOutNode[]; width: number; height: number } {
  const tree = measureTree(root, ctx, 0, fullText, 0, ROOT_COLOR)
  const height = Math.max(480, PAD_Y * 2 + minSpan(tree))
  assignPositions(tree, PAD_X, PAD_Y, height - PAD_Y)
  const nodes = flatten(tree)
  let maxRight = PAD_X
  let maxBottom = PAD_Y
  let minTop = height
  for (const n of nodes) {
    maxRight = Math.max(maxRight, n.x + 10 + n.w + 28)
    maxBottom = Math.max(maxBottom, n.y + n.h / 2 + 20)
    minTop = Math.min(minTop, n.y - n.h / 2 - 12)
  }
  const width = Math.ceil(maxRight + PAD_X)
  // If top clipped, shift all down
  if (minTop < 16) {
    const dy = 16 - minTop
    for (const n of nodes) {
      n.y += dy
      if (n.parentY != null) n.parentY += dy
    }
    maxBottom += dy
  }
  return { nodes, width, height: Math.ceil(Math.max(height, maxBottom + PAD_Y)) }
}

export function mindmapLogicalSize(root: MindmapNode, fullText = false): { width: number; height: number } {
  const leaves = countLeaves(root)
  return {
    width: 900,
    height: Math.max(480, PAD_Y * 2 + leaves * MIN_LEAF_SLOT),
  }
}

function drawBranch(
  ctx: CanvasRenderingContext2D,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  color: string,
  depth: number,
) {
  const midX = (x0 + x1) / 2
  ctx.beginPath()
  ctx.strokeStyle = color
  ctx.lineWidth = depth <= 1 ? 2.6 : depth === 2 ? 2.0 : 1.6
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.moveTo(x0, y0)
  ctx.bezierCurveTo(midX, y0, midX, y1, x1, y1)
  ctx.stroke()
}

function drawDot(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  fill: string,
  stroke?: string,
) {
  ctx.beginPath()
  ctx.arc(x, y, r, 0, Math.PI * 2)
  ctx.fillStyle = fill
  ctx.fill()
  if (stroke) {
    ctx.strokeStyle = stroke
    ctx.lineWidth = 1.5
    ctx.stroke()
  }
}

function drawLabelLines(
  ctx: CanvasRenderingContext2D,
  lines: string[],
  x: number,
  y: number,
  depth: number,
) {
  const lh = lineHeightFor(depth)
  const blockH = lines.length * lh + Math.max(0, lines.length - 1) * LINE_GAP
  let ty = y - blockH / 2 + lh / 2
  ctx.font = fontFor(depth)
  ctx.fillStyle = depth === 0 ? '#0f172a' : depth === 1 ? '#1e293b' : '#334155'
  ctx.textBaseline = 'middle'
  for (const line of lines) {
    ctx.fillText(line, x, ty)
    ty += lh + LINE_GAP
  }
}

/** Render mindmap onto a new canvas; returns the canvas (caller may toDataURL). */
export function renderMindmapToCanvas(
  rootIn: MindmapNode,
  opts: MindmapRenderOpts = {},
): HTMLCanvasElement | null {
  const scale = Math.max(1, opts.scale ?? 1)
  const fullText = opts.fullText ?? true
  const root = sanitizeTree(rootIn)

  const probe = document.createElement('canvas').getContext('2d')
  if (!probe) return null
  const { nodes, width: lw, height: lh } = layoutMindmap(root, probe, fullText)

  const canvas = document.createElement('canvas')
  canvas.width = Math.round(lw * scale)
  canvas.height = Math.round(lh * scale)
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  ctx.setTransform(scale, 0, 0, scale, 0, 0)

  ctx.fillStyle = '#f4f4f5'
  ctx.fillRect(0, 0, lw, lh)
  const wash = ctx.createLinearGradient(0, 0, lw, lh)
  wash.addColorStop(0, 'rgba(255,255,255,0.6)')
  wash.addColorStop(1, 'rgba(241,245,249,0.35)')
  ctx.fillStyle = wash
  ctx.fillRect(0, 0, lw, lh)

  for (const n of nodes) {
    if (n.parentX == null || n.parentY == null) continue
    drawBranch(ctx, n.parentX, n.parentY, n.x - 2, n.y, n.color, n.depth)
  }

  for (const n of nodes) {
    if (n.depth === 0) {
      drawDot(ctx, n.x - 2, n.y, 6.5, ROOT_COLOR)
      drawLabelLines(ctx, n.lines, n.x + 10, n.y, 0)
    } else {
      drawDot(ctx, n.x - 2, n.y, n.hasChildren ? 5 : 4, '#fff', n.color)
      drawLabelLines(ctx, n.lines, n.x + 10, n.y, n.depth)
    }
  }

  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = 'rgba(100,116,139,0.4)'
  ctx.font = '11px sans-serif'
  ctx.fillText('极速下 · AI 思维导图', Math.max(12, lw - 148), lh - 14)

  return canvas
}

export function mindmapToDataUrl(root: MindmapNode, opts?: MindmapRenderOpts): string | null {
  const canvas = renderMindmapToCanvas(root, opts)
  return canvas ? canvas.toDataURL('image/png') : null
}

export function downloadMindmapPng(root: MindmapNode, title?: string, scale = 2): void {
  const url = mindmapToDataUrl(root, { scale, fullText: true })
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.download = `${cleanMindmapLabel(title || 'mindmap').slice(0, 24) || 'mindmap'}-mindmap.png`
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/**
 * The documentation renderer.
 *
 * Docs arrive from the server as blocks — paragraphs, headings, code, notes,
 * tables, definition lists, cards — not as Markdown, so they render with the
 * same component library as the rest of the app. The block set is closed, so
 * the switch below is exhaustive.
 */

import { Link } from '@inertiajs/react'
import type { ReactNode } from 'react'
import { cx } from '@/js/hooks'
import { Table, TBody, TD, TH, THead, TR } from './kit'

export type Block = {
  type: string
  text?: string
  level?: number
  code?: string
  lang?: string
  caption?: string
  items?: any[] // eslint-disable-line @typescript-eslint/no-explicit-any
  ordered?: boolean
  tone?: string
  title?: string
  head?: string[]
  rows?: string[][]
}

export type DocPage = {
  slug: string
  section: string
  title: string
  summary: string
  blocks: Block[]
}

/** Must match `routes/web/docs.py::_anchor`. */
export function anchor(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '-')
    .replace(/^-+|-+$/g, '')
}

/**
 * Inline markup: `code`, **bold**, *italic*, [links](/docs/...). A deliberately
 * tiny subset parsed in one pass — not a Markdown library. Bold is matched
 * before italic or `**text**` is consumed as an empty italic plus a stray star.
 */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(\[[^\]]+\]\([^)]+\))/g
  let last = 0
  let match: RegExpExecArray | null
  let key = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index))
    const token = match[0]
    if (token.startsWith('`')) {
      out.push(
        <code
          key={key++}
          className="mono rounded-[var(--radius-xs)] bg-sunken px-1.5 py-0.5 text-[0.9em] text-ink"
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else if (token.startsWith('**')) {
      out.push(
        <strong key={key++} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('*')) {
      out.push(
        <em key={key++} className="italic">
          {token.slice(1, -1)}
        </em>,
      )
    } else {
      const [, label, href] = token.match(/\[([^\]]+)\]\(([^)]+)\)/) ?? []
      const internal = href?.startsWith('/')
      out.push(
        internal ? (
          <Link key={key++} href={href!} className="font-medium text-brand hover:underline">
            {label}
          </Link>
        ) : (
          <a
            key={key++}
            href={href}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-brand hover:underline"
          >
            {label}
          </a>
        ),
      )
    }
    last = pattern.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function paragraphs(text: string): ReactNode {
  return text.split('\n\n').map((part, index) => (
    <p key={index} className={index > 0 ? 'mt-2' : undefined}>
      {inline(part)}
    </p>
  ))
}

const NOTE_TONE: Record<string, { wrap: string; mark: string; label: string }> = {
  info: { wrap: 'border-brand/25 bg-brand-soft', mark: 'bg-brand', label: 'text-brand' },
  caution: { wrap: 'border-caution/30 bg-caution-soft', mark: 'bg-caution', label: 'text-caution' },
  critical: { wrap: 'border-critical/30 bg-critical-soft', mark: 'bg-critical', label: 'text-critical' },
  ok: { wrap: 'border-ok/30 bg-ok-soft', mark: 'bg-ok', label: 'text-ok' },
}

export function Blocks({ blocks }: { blocks: Block[] }) {
  return (
    <div className="space-y-5 text-[14px] leading-[1.65] text-ink-muted">
      {blocks.map((block, index) => (
        <BlockView key={index} block={block} />
      ))}
    </div>
  )
}

function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case 'p':
      return <p>{inline(block.text ?? '')}</p>

    case 'h': {
      const id = anchor(block.text ?? '')
      const level = block.level ?? 2
      return level <= 2 ? (
        <h2 id={id} className="scroll-mt-24 pt-3 text-[16px] font-semibold tracking-[-0.01em] text-ink">
          {inline(block.text ?? '')}
        </h2>
      ) : (
        <h3 id={id} className="scroll-mt-24 pt-2 text-[14.5px] font-semibold text-ink">
          {inline(block.text ?? '')}
        </h3>
      )
    }

    case 'code':
      return (
        <figure>
          <pre className="overflow-x-auto rounded-[var(--radius-sm)] border border-line bg-sunken px-4 py-3.5">
            <code className="mono text-[12.5px] leading-[1.6] text-ink">{block.code}</code>
          </pre>
          {block.caption && (
            <figcaption className="mt-1.5 text-[12px] text-ink-faint">{block.caption}</figcaption>
          )}
        </figure>
      )

    case 'list': {
      const Tag = block.ordered ? 'ol' : 'ul'
      return (
        <Tag className={cx('space-y-2 pl-1', block.ordered && 'list-inside list-decimal')}>
          {(block.items ?? []).map((item: string, index: number) => (
            <li key={index} className="flex gap-2.5">
              {!block.ordered && <span className="dot mt-[0.55em] shrink-0 bg-ink-faint" aria-hidden />}
              <span>{inline(item)}</span>
            </li>
          ))}
        </Tag>
      )
    }

    case 'note': {
      const tone = NOTE_TONE[block.tone ?? 'info'] ?? NOTE_TONE.info
      return (
        <aside className={cx('rounded-[var(--radius-sm)] border px-4 py-3.5', tone.wrap)}>
          {block.title && (
            <p className={cx('mb-1 flex items-center gap-2 text-[13px] font-semibold', tone.label)}>
              <span className={cx('dot', tone.mark)} aria-hidden />
              {block.title}
            </p>
          )}
          <div className="text-[13.5px] leading-[1.6] text-ink-muted">{paragraphs(block.text ?? '')}</div>
        </aside>
      )
    }

    case 'table':
      return (
        <div className="surface overflow-hidden">
          <Table>
            <THead>
              <TR>
                {(block.head ?? []).map((cell) => (
                  <TH key={cell}>{cell}</TH>
                ))}
              </TR>
            </THead>
            <TBody>
              {(block.rows ?? []).map((row, index) => (
                <TR key={index}>
                  {row.map((cell, cellIndex) => (
                    <TD key={cellIndex}>{inline(cell)}</TD>
                  ))}
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      )

    case 'terms':
      return (
        <dl className="space-y-3">
          {(block.items ?? []).map((item: { term: string; text: string }) => (
            <div key={item.term} className="border-l-2 border-line pl-3.5">
              <dt className="text-[13.5px] font-semibold text-ink">{item.term}</dt>
              <dd className="mt-0.5">{inline(item.text)}</dd>
            </div>
          ))}
        </dl>
      )

    case 'cards':
      return (
        <div className="grid gap-3 sm:grid-cols-2">
          {(block.items ?? []).map((item: { title: string; text: string }) => (
            <div key={item.title} className="surface p-4">
              <p className="text-[13.5px] font-semibold text-ink">{item.title}</p>
              <p className="mt-1 text-[13px] leading-[1.6]">{inline(item.text)}</p>
            </div>
          ))}
        </div>
      )

    default:
      return null
  }
}

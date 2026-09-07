/** A read-only JSON block with light syntax colouring and a copy action. */

import { useCopy } from '@/js/hooks'
import { Button } from './kit'

function highlight(value: unknown): string {
  const json = JSON.stringify(value, null, 2)
  return json.replace(
    /("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let cls = 'text-brand' // number
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? 'text-ink font-medium' : 'text-ok'
      } else if (/true|false/.test(match)) {
        cls = 'text-caution'
      } else if (/null/.test(match)) {
        cls = 'text-ink-faint'
      }
      return `<span class="${cls}">${match}</span>`
    },
  )
}

export function JsonBlock({ value, className = '' }: { value: unknown; className?: string }) {
  const [copied, copy] = useCopy()
  return (
    <div className={`surface relative overflow-hidden ${className}`}>
      <Button
        size="xs"
        className="absolute right-2 top-2 z-10"
        onClick={() => copy(JSON.stringify(value, null, 2))}
      >
        {copied ? 'Copied' : 'Copy'}
      </Button>
      <pre className="max-h-[520px] overflow-auto p-4 text-[12px] leading-relaxed">
        <code
          className="font-mono"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: highlight(value) }}
        />
      </pre>
    </div>
  )
}

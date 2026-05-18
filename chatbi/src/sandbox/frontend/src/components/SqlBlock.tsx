import { useState } from 'react'

interface Props {
  sql: string
}

export default function SqlBlock({ sql }: Props) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        <span>{open ? '▼' : '▶'}</span>
        <span>查看 SQL</span>
      </button>
      {open && (
        <pre className="mt-1 p-3 bg-gray-100 rounded text-xs font-mono text-gray-700 overflow-x-auto whitespace-pre-wrap border border-gray-200">
          {sql}
        </pre>
      )}
    </div>
  )
}

import ChartPanel from './ChartPanel'
import SqlBlock from './SqlBlock'
import type { Message } from '../types'

interface Props {
  message: Message
}

export default function MessageBubble({ message }: Props) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[70%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[85%] bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-gray-100">
        {message.loading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <span className="animate-pulse">●</span>
            <span className="animate-pulse delay-75">●</span>
            <span className="animate-pulse delay-150">●</span>
          </div>
        ) : (
          <>
            {message.error ? (
              <p className="text-red-500 text-sm">{message.content}</p>
            ) : (
              <p className="text-gray-800 text-sm leading-relaxed">{message.content}</p>
            )}
            {message.chart && message.resultRows && !message.error && (
              <ChartPanel chart={message.chart} rows={message.resultRows} />
            )}
            {message.sql && !message.error && (
              <SqlBlock sql={message.sql} />
            )}
          </>
        )}
      </div>
    </div>
  )
}

import { useState, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import ChatWindow from './components/ChatWindow'
import InputBar from './components/InputBar'
import { sendChat, resetSession } from './api'
import type { Message } from './types'

const SESSION_KEY = 'chatbi_session_id'

function getOrCreateSession(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = uuidv4()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

const WELCOME: Message = {
  id: 'welcome',
  role: 'assistant',
  content: '你好！我是 ChatBI 助手。请用自然语言提问，我会帮你查询数据并生成图表。\n\n示例：\n• 上季度各地区销售额是多少？\n• 2024年各月销售趋势\n• 各产品类别销售额占比',
}

export default function App() {
  const [sessionId] = useState(getOrCreateSession)
  const [messages, setMessages] = useState<Message[]>([WELCOME])
  const [loading, setLoading] = useState(false)

  const handleSend = useCallback(async (question: string) => {
    const userMsg: Message = { id: uuidv4(), role: 'user', content: question }
    const loadingMsg: Message = { id: uuidv4(), role: 'assistant', content: '', loading: true }

    setMessages(prev => [...prev, userMsg, loadingMsg])
    setLoading(true)

    try {
      const res = await sendChat(question, sessionId)
      const assistantMsg: Message = {
        id: loadingMsg.id,
        role: 'assistant',
        content: res.error ? `查询遇到问题：${res.error}` : res.insight,
        sql: res.sql,
        chart: res.chart ?? undefined,
        resultRows: res.result,
        error: res.error ?? undefined,
      }
      setMessages(prev => prev.map(m => m.id === loadingMsg.id ? assistantMsg : m))
    } catch (err) {
      const errMsg: Message = {
        id: loadingMsg.id,
        role: 'assistant',
        content: '网络连接失败，请检查后端服务是否已启动（localhost:8000）',
        error: String(err),
      }
      setMessages(prev => prev.map(m => m.id === loadingMsg.id ? errMsg : m))
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  const handleReset = async () => {
    try { await resetSession(sessionId) } catch { /* ignore */ }
    setMessages([WELCOME])
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <header className="flex items-center justify-between px-6 py-3 bg-gray-900 text-white shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center text-sm font-bold">
            BI
          </div>
          <div>
            <h1 className="text-sm font-semibold">ChatBI Sandbox</h1>
            <p className="text-xs text-gray-400">华为云 MaaS · 零售演示数据</p>
          </div>
        </div>
        <button
          onClick={handleReset}
          className="text-xs text-gray-400 hover:text-white border border-gray-600 hover:border-gray-400 px-3 py-1.5 rounded-lg transition-colors"
        >
          重置对话
        </button>
      </header>

      <ChatWindow messages={messages} />
      <InputBar onSend={handleSend} disabled={loading} />
    </div>
  )
}

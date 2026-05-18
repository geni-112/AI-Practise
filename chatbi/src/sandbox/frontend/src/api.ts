import axios from 'axios'
import type { ChartOption } from './types'

export interface ChatResponse {
  sql: string
  result: Record<string, unknown>[]
  chart: ChartOption | null
  insight: string
  cached: boolean
  error: string | null
}

export async function sendChat(question: string, sessionId: string): Promise<ChatResponse> {
  const response = await axios.post<ChatResponse>('/api/chat', {
    question,
    session_id: sessionId,
  })
  return response.data
}

export async function resetSession(sessionId: string): Promise<void> {
  await axios.delete(`/api/session/${sessionId}`)
}

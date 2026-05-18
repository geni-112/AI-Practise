export interface ChartOption {
  type: 'bar' | 'line' | 'pie' | 'table'
  option: Record<string, unknown>
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sql?: string
  chart?: ChartOption
  resultRows?: Record<string, unknown>[]
  error?: string
  loading?: boolean
}

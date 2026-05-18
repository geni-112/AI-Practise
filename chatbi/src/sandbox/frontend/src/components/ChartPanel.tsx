import ReactECharts from 'echarts-for-react'
import type { ChartOption } from '../types'

interface Props {
  chart: ChartOption
  rows: Record<string, unknown>[]
}

export default function ChartPanel({ chart, rows }: Props) {
  if (chart.type === 'table') {
    if (!rows || rows.length === 0) return null
    const cols = Object.keys(rows[0])
    return (
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-100">
              {cols.map(c => (
                <th key={c} className="px-3 py-2 text-left font-medium text-gray-600 border border-gray-200">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 50).map((row, i) => (
              <tr key={i} className="hover:bg-gray-50">
                {cols.map(c => (
                  <td key={c} className="px-3 py-2 border border-gray-200 text-gray-700">
                    {String(row[c] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > 50 && (
          <p className="mt-1 text-xs text-gray-400">显示前50行，共 {rows.length} 行</p>
        )}
      </div>
    )
  }

  return (
    <div className="mt-3">
      <ReactECharts
        option={chart.option}
        style={{ height: '300px', width: '100%' }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  )
}

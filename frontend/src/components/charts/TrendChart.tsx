import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TrendPoint } from '@/api/types'
import { cn } from '@/lib/cn'
import { fmt, shortDate } from '@/lib/format'

type Metric = 'position' | 'clicks' | 'impressions'
const LABEL: Record<Metric, string> = { position: 'Average position', clicks: 'Clicks', impressions: 'Impressions' }

/**
 * Single-series line: 2px ink stroke, recessive dashed grid, crosshair + tooltip.
 * Position is plotted on a reversed axis so "up" always means "better".
 */
export function TrendChart({ data, height = 260, className }: { data: TrendPoint[]; height?: number; className?: string }) {
  const [metric, setMetric] = useState<Metric>('position')
  const points = data.map((d) => ({ ...d, label: shortDate(d.day) }))
  const reversed = metric === 'position'
  const hasData = points.some((p) => p[metric] != null)

  return (
    <div className={className}>
      <div className="mb-3 flex items-center gap-4">
        <div className="flex items-center gap-2 text-sm text-ink-2">
          <span className="inline-block h-[3px] w-4 rounded bg-ink" />
          {LABEL[metric]}
          {reversed && <span className="text-xs text-ink-3">· 1 is the top</span>}
        </div>
        <div className="ml-auto flex rounded-lg bg-line-2 p-0.5 text-xs font-medium">
          {(['position', 'clicks', 'impressions'] as Metric[]).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={cn('rounded-md px-2.5 py-1 capitalize transition-all', metric === m ? 'bg-surface text-ink shadow-sm' : 'text-ink-3 hover:text-ink')}
            >
              {m}
            </button>
          ))}
        </div>
      </div>
      <div style={{ height }} className="relative">
        {!hasData && (
          <div className="absolute inset-0 z-10 grid place-items-center text-sm text-ink-3">
            No Search Console data yet — connect it in Settings and run a rank sync.
          </div>
        )}
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid vertical={false} stroke="#e6e6e6" strokeDasharray="4 4" />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: '#e6e6e6' }} tick={{ fill: '#4b4b4b', fontSize: 12 }} minTickGap={36} dy={6} />
            <YAxis
              reversed={reversed}
              domain={reversed ? [1, 'auto'] : [0, 'auto']}
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              tick={{ fill: '#4b4b4b', fontSize: 12 }}
              width={44}
              tickFormatter={(v: number) => (v >= 1000 ? `${Math.round(v / 100) / 10}k` : String(v))}
            />
            <Tooltip
              cursor={{ stroke: '#111', strokeWidth: 1, strokeDasharray: '3 3' }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const p = payload[0].payload as TrendPoint & { label: string }
                return (
                  <div className="card px-3 py-2 text-xs shadow-lift">
                    <div className="font-semibold">{p.label}</div>
                    <div className="mt-1 grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 text-ink-2">
                      <span>Position</span>
                      <span className="text-right font-medium text-ink tabular-nums">{p.position ?? '—'}</span>
                      <span>Clicks</span>
                      <span className="text-right font-medium text-ink tabular-nums">{fmt(p.clicks)}</span>
                      <span>Impressions</span>
                      <span className="text-right font-medium text-ink tabular-nums">{fmt(p.impressions)}</span>
                    </div>
                  </div>
                )
              }}
            />
            <Line
              type="monotone"
              dataKey={metric}
              stroke="#111"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, fill: '#111', stroke: '#fff', strokeWidth: 2 }}
              connectNulls
              isAnimationActive
              animationDuration={900}
              animationEasing="ease-out"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

import { AnimatePresence, motion } from 'framer-motion'
import { Plus, Search, Star, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import { useAddKeyword, useKeywordHistory, useKeywords, useOverview, useRunRankSync, useUpdateKeyword } from '@/api/hooks'
import type { Keyword } from '@/api/types'
import { Button } from '@/components/ui/Button'
import { Card, Chip, Empty, PageMotion, Skeleton, fadeUp } from '@/components/ui/primitives'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { fmt, humanize } from '@/lib/format'
import { useSite } from '@/lib/site'

const BUCKETS = [
  { key: '', label: 'All' },
  { key: 'striking_distance', label: 'Striking distance', hint: 'Positions 4–20 with real impressions: the best return on a small push' },
  { key: 'defend', label: 'Defend', hint: 'Top 3 — protect these' },
  { key: 'long_tail', label: 'Long tail' },
  { key: 'suggested', label: 'Suggested', hint: 'New terms the Keyword Scout proposed' },
]

export function Keywords() {
  const { site } = useSite()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const [bucket, setBucket] = useState('')
  const [selected, setSelected] = useState<Keyword | null>(null)
  const [adding, setAdding] = useState(false)
  const [newTerm, setNewTerm] = useState('')
  const toast = useToast()
  const showDrops = params.get('view') === 'drops'

  const filter = bucket === 'suggested' ? { source: 'suggested' } : bucket ? { bucket } : {}
  const { data: keywords, isLoading } = useKeywords(site.id, { ...filter, q: q || undefined })
  const { data: ov } = useOverview(site.id)
  const update = useUpdateKeyword(site.id)
  const add = useAddKeyword(site.id)
  const sync = useRunRankSync(site.id)

  const maxImp = useMemo(() => Math.max(1, ...(keywords?.map((k) => k.impressions_28d) ?? [1])), [keywords])

  const submitAdd = () => {
    if (!newTerm.trim()) return
    add.mutate(
      { term: newTerm, tracked: true },
      {
        onSuccess: () => {
          setNewTerm('')
          setAdding(false)
          toast({ tone: 'success', title: 'Keyword tracked', detail: 'The Ranker will report its position after the next sync.' })
        },
        onError: (e) => toast({ tone: 'error', title: 'Could not add keyword', detail: e.message }),
      },
    )
  }

  return (
    <PageMotion className="flex flex-col gap-4">
      {showDrops && ov && (
        <Card className="border-l-4 border-l-bad p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Ranking drops this week</h2>
            <button className="btn btn-ghost btn-sm" onClick={() => setParams({})}>
              <X className="size-4" /> Close
            </button>
          </div>
          {ov.recent_drops.length === 0 ? (
            <p className="mt-2 text-sm text-ink-3">No drops above the threshold.</p>
          ) : (
            <ul className="mt-3 flex flex-col gap-2">
              {ov.recent_drops.map((d, i) => (
                <li key={i} className="flex items-center gap-3 text-sm">
                  <span className="font-medium">{d.keyword}</span>
                  <span className="text-ink-3">{d.page?.replace(site.url, '') || d.page}</span>
                  <span className="ml-auto tabular-nums">
                    {d.from} → <span className="font-semibold text-bad">{d.to}</span>
                  </span>
                  {d.suspect_change_sets?.length ? <Chip tone="bad">after change set</Chip> : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <Card className="p-0">
        <div className="flex flex-wrap items-center gap-3 px-6 pt-6 pb-4">
          <div className="flex rounded-lg bg-line-2 p-0.5 text-sm font-medium">
            {BUCKETS.map((b) => (
              <button
                key={b.key}
                title={b.hint}
                onClick={() => setBucket(b.key)}
                className={cn('relative rounded-md px-3 py-1.5 transition-colors', bucket === b.key ? 'text-ink' : 'text-ink-3 hover:text-ink')}
              >
                {bucket === b.key && <motion.span layoutId="kw-tab" className="absolute inset-0 rounded-md bg-surface shadow-sm" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
                <span className="relative">{b.label}</span>
              </button>
            ))}
          </div>
          <label className="relative ml-auto">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
            <input className="input w-64 pl-9" placeholder="Search keywords" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
          <Button variant="secondary" size="sm" onClick={() => sync.mutate(undefined, { onSuccess: () => toast({ tone: 'info', title: 'Rank sync queued' }) })} loading={sync.isPending}>
            Sync Search Console
          </Button>
          <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setAdding((v) => !v)}>
            Track keyword
          </Button>
        </div>

        <AnimatePresence initial={false}>
          {adding && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
              <div className="flex items-center gap-2 border-t border-line bg-brand-tint/50 px-6 py-3">
                <input
                  autoFocus
                  className="input max-w-md"
                  placeholder="e.g. running shoes for flat feet"
                  value={newTerm}
                  onChange={(e) => setNewTerm(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && submitAdd()}
                />
                <Button size="sm" onClick={submitAdd} loading={add.isPending}>
                  Add
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
                  Cancel
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="grid grid-cols-[1fr_auto] border-t border-line">
          <div className="min-w-0">
            <div className="grid grid-cols-[minmax(0,1fr)_120px_90px_90px_150px_60px] gap-3 px-6 py-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">
              <span>Keyword</span>
              <span>Page</span>
              <span className="text-right">Position</span>
              <span className="text-right">Clicks</span>
              <span>Impressions · 28d</span>
              <span className="text-right">Track</span>
            </div>
            {isLoading ? (
              <div className="flex flex-col gap-3 px-6 pb-6">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            ) : !keywords?.length ? (
              <Empty
                icon={<Search className="size-5" />}
                title="No keywords yet"
                hint={ov?.integrations.gsc ? 'Run a rank sync to pull queries from Search Console.' : 'Connect Google Search Console in Settings, or track keywords by hand.'}
              />
            ) : (
              <motion.ul variants={{ show: { transition: { staggerChildren: 0.025 } } }} initial="hidden" animate="show" className="pb-2">
                {keywords.map((k) => (
                  <motion.li
                    key={k.id}
                    variants={fadeUp}
                    onClick={() => setSelected(selected?.id === k.id ? null : k)}
                    className={cn('row-hover grid cursor-pointer grid-cols-[minmax(0,1fr)_120px_90px_90px_150px_60px] items-center gap-3 border-t border-line-2 px-6 py-3 text-sm', selected?.id === k.id && 'bg-brand-tint/60')}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-medium">{k.term}</span>
                        {k.bucket === 'striking_distance' && <Chip tone="brand">opportunity {k.opportunity}</Chip>}
                        {k.source === 'suggested' && <Chip tone="info">suggested</Chip>}
                        {k.intent !== 'unknown' && <span className="text-xs text-ink-3">{k.intent}</span>}
                      </div>
                    </div>
                    <span className="truncate text-ink-3">{k.target_path ?? '—'}</span>
                    <span className="text-right tabular-nums">{k.position_28d ?? '—'}</span>
                    <span className="text-right tabular-nums">{fmt(k.clicks_28d)}</span>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-2">
                        <motion.div className="h-full rounded-full bg-ink" initial={{ width: 0 }} animate={{ width: `${(k.impressions_28d / maxImp) * 100}%` }} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }} />
                      </div>
                      <span className="w-12 text-right text-xs tabular-nums">{fmt(k.impressions_28d)}</span>
                    </div>
                    <div className="text-right">
                      <button
                        aria-label={k.tracked ? 'Untrack' : 'Track'}
                        onClick={(e) => {
                          e.stopPropagation()
                          update.mutate({ id: k.id, tracked: !k.tracked })
                        }}
                        className="btn btn-ghost btn-icon"
                      >
                        <motion.span whileTap={{ scale: 0.7 }} className="inline-flex">
                          <Star className={cn('size-4 transition-colors', k.tracked ? 'fill-brand text-brand-3' : 'text-ink-3')} />
                        </motion.span>
                      </button>
                    </div>
                  </motion.li>
                ))}
              </motion.ul>
            )}
          </div>

          <AnimatePresence>
            {selected && (
              <motion.aside
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 360, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ type: 'spring', stiffness: 300, damping: 34 }}
                className="overflow-hidden border-l border-line"
              >
                <KeywordPanel keyword={selected} onClose={() => setSelected(null)} />
              </motion.aside>
            )}
          </AnimatePresence>
        </div>
      </Card>
    </PageMotion>
  )
}

function KeywordPanel({ keyword, onClose }: { keyword: Keyword; onClose: () => void }) {
  const { data: history } = useKeywordHistory(keyword.id)
  const daily = useMemo(() => {
    if (!history) return []
    const m = new Map<string, { day: string; pos: number; w: number; clicks: number }>()
    for (const r of history) {
      const d = m.get(r.day) ?? { day: r.day, pos: 0, w: 0, clicks: 0 }
      d.pos += r.position * Math.max(1, r.impressions)
      d.w += Math.max(1, r.impressions)
      d.clicks += r.clicks
      m.set(r.day, d)
    }
    return [...m.values()].map((d) => ({ day: d.day, position: Math.round((d.pos / d.w) * 10) / 10, clicks: d.clicks }))
  }, [history])
  return (
    <div className="w-[360px] p-5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{keyword.term}</h3>
          <p className="text-xs text-ink-3">{keyword.bucket ? humanize(keyword.bucket) : humanize(keyword.source)}</p>
        </div>
        <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
          <X className="size-4" />
        </button>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        {[
          ['Position', keyword.position_28d ?? '—'],
          ['Clicks', fmt(keyword.clicks_28d)],
          ['Opportunity', keyword.opportunity],
        ].map(([l, v]) => (
          <div key={l as string} className="rounded-lg bg-line-2 px-2 py-2">
            <div className="text-lg font-semibold tabular-nums">{v}</div>
            <div className="text-[11px] text-ink-3">{l}</div>
          </div>
        ))}
      </div>
      <div className="mt-5 text-xs font-semibold tracking-wide text-ink-3 uppercase">Position · 90 days</div>
      <div className="mt-2 h-32">
        {daily.length > 1 ? (
          <ResponsiveContainer>
            <LineChart data={daily} margin={{ top: 6, right: 4, bottom: 0, left: 0 }}>
              <YAxis reversed domain={[1, 'auto']} hide />
              <Tooltip
                cursor={{ stroke: '#111', strokeDasharray: '3 3' }}
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <div className="card px-2 py-1 text-xs shadow-lift">
                      {(payload[0].payload as { day: string }).day} · pos <b>{(payload[0].payload as { position: number }).position}</b>
                    </div>
                  ) : null
                }
              />
              <Line type="monotone" dataKey="position" stroke="#111" strokeWidth={2} dot={false} isAnimationActive animationDuration={700} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-ink-3">Not enough history yet.</p>
        )}
      </div>
      {keyword.notes && <p className="mt-4 rounded-lg bg-brand-tint px-3 py-2 text-sm">{keyword.notes}</p>}
      {keyword.target_path && (
        <p className="mt-3 text-xs text-ink-3">
          Target page <span className="font-medium text-ink">{keyword.target_path}</span>
        </p>
      )}
    </div>
  )
}

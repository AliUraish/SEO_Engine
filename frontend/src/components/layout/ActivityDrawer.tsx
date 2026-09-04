import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, Bot, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useEvents } from '@/api/hooks'
import type { AgentEvent } from '@/api/types'
import { cn } from '@/lib/cn'
import { humanize, timeAgo } from '@/lib/format'

const AGENT_COLOR: Record<string, string> = {
  crawler: 'bg-info',
  auditor: 'bg-brand',
  'keyword-scout': 'bg-good',
  fixer: 'bg-ink',
  verifier: 'bg-warn',
  ranker: 'bg-bad',
  'migration-advisor': 'bg-ink-3',
}

/** Live agent feed: initial page from REST, then SSE appends. */
export function useLiveEvents(siteId: string) {
  const { data: initial } = useEvents(siteId)
  const [live, setLive] = useState<AgentEvent[]>([])
  const [unseen, setUnseen] = useState(0)
  const qc = useQueryClient()

  useEffect(() => {
    setLive([])
    const es = new EventSource(`/api/sites/${siteId}/events/stream`)
    es.addEventListener('agent', (e) => {
      const ev = JSON.parse((e as MessageEvent).data) as AgentEvent
      setLive((xs) => [...xs, ev])
      setUnseen((n) => n + 1)
      // agents changed something: refresh what the dashboard shows
      for (const key of ['overview', 'issues', 'pages', 'change-sets', 'keywords', 'jobs', 'crawls', 'migrations', 'score-history']) qc.invalidateQueries({ queryKey: [key, siteId] })
    })
    return () => es.close()
  }, [siteId, qc])

  const events = useMemo(() => {
    const seen = new Set<string>()
    return [...(initial ?? []), ...live].filter((e) => (seen.has(e.id) ? false : (seen.add(e.id), true)))
  }, [initial, live])
  return { events, unseen, clearUnseen: () => setUnseen(0) }
}

export function ActivityDrawer({ open, onClose, events }: { open: boolean; onClose: () => void; events: AgentEvent[] }) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[2px]" onClick={onClose} />
          <motion.aside
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 380, damping: 36 }}
            className="fixed inset-y-3 right-3 z-50 flex w-[440px] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-2xl bg-surface shadow-lift"
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <div className="flex items-center gap-2">
                <Bot className="size-5" />
                <h2 className="font-semibold">Agent activity</h2>
                <span className="pulse-dot ml-1 inline-block size-2 rounded-full bg-good text-good" />
              </div>
              <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
                <X className="size-5" />
              </button>
            </div>
            <div className="scroll-thin flex-1 overflow-y-auto px-5 py-4">
              {events.length === 0 ? (
                <p className="py-10 text-center text-sm text-ink-3">No activity yet. Run a crawl to wake the agents.</p>
              ) : (
                <ol className="relative flex flex-col gap-3 border-l border-line pl-5">
                  {[...events].reverse().map((e, i) => (
                    <motion.li key={e.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i, 8) * 0.03 }} className="relative">
                      <span className={cn('absolute top-1.5 -left-[25px] size-2.5 rounded-full ring-4 ring-surface', AGENT_COLOR[e.agent] ?? 'bg-ink-3')} />
                      <div className="flex items-center gap-2 text-xs text-ink-3">
                        <span className="font-semibold text-ink">{humanize(e.agent)}</span>
                        <span>{timeAgo(e.created_at)}</span>
                        {e.level === 'error' && <span className="rounded bg-bad-tint px-1.5 py-0.5 font-semibold text-bad">error</span>}
                        {e.level === 'warn' && <span className="rounded bg-warn-tint px-1.5 py-0.5 font-semibold text-warn">warning</span>}
                      </div>
                      <p className={cn('mt-0.5 text-sm', e.level === 'handoff' && 'flex items-center gap-1.5 text-ink-2')}>
                        {e.level === 'handoff' && <ArrowRight className="size-3.5" />}
                        {e.level === 'handoff' ? `handed off to ${e.message.replace(/^→\s*/, '')}` : e.message}
                      </p>
                    </motion.li>
                  ))}
                </ol>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

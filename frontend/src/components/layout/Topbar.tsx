import { AnimatePresence, motion } from 'framer-motion'
import { Activity, Check, ChevronDown, CircleHelp, Globe, Play, Plus, UserRound } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { useJobs, useRunCrawl } from '@/api/hooks'
import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { useSite } from '@/lib/site'

function useClickAway(onAway: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onAway()
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [onAway])
  return ref
}

function Menu({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -6, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -4, scale: 0.98 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          className="card absolute right-0 top-[calc(100%+8px)] z-30 min-w-[240px] overflow-hidden p-1.5 shadow-lift"
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function Topbar({ title, onOpenActivity, liveCount }: { title: string; onOpenActivity: () => void; liveCount: number }) {
  const { site, sites, select } = useSite()
  const nav = useNavigate()
  const toast = useToast()
  const run = useRunCrawl(site.id)
  const { data: jobs } = useJobs(site.id)
  const crawling = jobs?.some((j) => j.type === 'crawl.site' && (j.status === 'running' || j.status === 'queued')) ?? false
  const [ok, setOk] = useState(false)
  const [menu, setMenu] = useState<null | 'help' | 'account'>(null)
  const away = useClickAway(() => setMenu(null))

  const onRun = () =>
    run.mutate(undefined, {
      onSuccess: () => {
        setOk(true)
        setTimeout(() => setOk(false), 1600)
        toast({ tone: 'success', title: 'Crawl queued', detail: 'The Crawler will hand off to the Auditor when it finishes.' })
      },
      onError: (e) => toast({ tone: 'error', title: 'Could not start crawl', detail: e.message }),
    })

  return (
    <header className="flex h-[88px] shrink-0 items-center justify-between border-b border-line bg-surface px-10">
      <h1 className="text-[1.55rem] font-semibold tracking-tight">{title}</h1>
      <div className="flex items-center gap-3" ref={away}>
        <Button onClick={onRun} loading={run.isPending} success={ok} disabled={crawling} icon={crawling ? <span className="pulse-dot inline-block size-2 rounded-full bg-ink" /> : <Play className="size-4" />}>
          {crawling ? 'Crawling…' : 'Run crawl'}
        </Button>

        <button
          onClick={onOpenActivity}
          className="btn btn-ghost btn-icon relative ml-1"
          aria-label="Agent activity"
          title="Agent activity"
        >
          <Activity className="size-5" strokeWidth={1.8} />
          {liveCount > 0 && (
            <motion.span
              key={liveCount}
              initial={{ scale: 0.5 }}
              animate={{ scale: 1 }}
              className="absolute -top-0.5 -right-0.5 grid min-w-[18px] place-items-center rounded-full bg-brand px-1 text-[10px] font-bold"
            >
              {liveCount > 9 ? '9+' : liveCount}
            </motion.span>
          )}
        </button>
        <div className="mx-1 h-8 w-px bg-line" />

        <div className="relative">
          <button className={cn('btn btn-ghost btn-icon', menu === 'help' && 'bg-black/5')} aria-label="Help" onClick={() => setMenu(menu === 'help' ? null : 'help')}>
            <CircleHelp className="size-6" strokeWidth={1.6} />
          </button>
          <Menu open={menu === 'help'}>
            <div className="px-3 py-2 text-xs font-semibold tracking-wide text-ink-3 uppercase">How SEO Engine works</div>
            {[
              ['Crawler', 'fetches every page and stores a snapshot'],
              ['Auditor', 'scores pages against 34 SEO rules'],
              ['Keyword Scout', 'mines Search Console for opportunities'],
              ['Fixer', 'drafts changes — you approve on the Changes page'],
              ['Verifier', 're-crawls after merge to confirm the fix is live'],
              ['Ranker', 'syncs rankings daily and flags drops'],
            ].map(([a, d]) => (
              <div key={a} className="rounded-lg px-3 py-2 text-sm hover:bg-black/[0.04]">
                <span className="font-medium">{a}</span> <span className="text-ink-3">— {d}</span>
              </div>
            ))}
          </Menu>
        </div>

        <div className="relative">
          <button className={cn('btn btn-ghost flex items-center gap-1.5 rounded-full py-1.5 pr-2 pl-1.5', menu === 'account' && 'bg-black/5')} onClick={() => setMenu(menu === 'account' ? null : 'account')}>
            <span className="grid size-8 place-items-center rounded-full border border-line">
              <UserRound className="size-5" strokeWidth={1.6} />
            </span>
            <ChevronDown className="size-4 text-ink-3" />
          </button>
          <Menu open={menu === 'account'}>
            <div className="px-3 py-2 text-xs font-semibold tracking-wide text-ink-3 uppercase">Sites</div>
            {sites.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  select(s.id)
                  setMenu(null)
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-black/[0.04]"
              >
                <Globe className="size-4 text-ink-3" />
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{s.name}</span> <span className="text-ink-3">{s.url.replace(/^https?:\/\//, '')}</span>
                </span>
                {s.id === site.id && <Check className="size-4 text-good" />}
              </button>
            ))}
            <div className="my-1 h-px bg-line" />
            <button
              onClick={() => {
                setMenu(null)
                nav('/settings?add=1')
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-black/[0.04]"
            >
              <Plus className="size-4" /> Add site
            </button>
          </Menu>
        </div>
      </div>
    </header>
  )
}

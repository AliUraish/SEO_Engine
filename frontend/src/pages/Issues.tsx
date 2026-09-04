import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, ChevronDown, EyeOff, Lightbulb, RotateCcw, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useIssues, useRules, useUpdateIssue } from '@/api/hooks'
import type { Issue, Severity } from '@/api/types'
import { Button } from '@/components/ui/Button'
import { Card, Chip, Empty, PageMotion, SeverityDot, Skeleton, fadeUp } from '@/components/ui/primitives'
import { cn } from '@/lib/cn'
import { SEVERITY_LABEL, SEVERITY_ORDER, timeAgo } from '@/lib/format'
import { useSite } from '@/lib/site'

export function Issues() {
  const { site } = useSite()
  const [params, setParams] = useSearchParams()
  const rule = params.get('rule') ?? ''
  const [severity, setSeverity] = useState<Severity | ''>('')
  const [status, setStatus] = useState<'open' | 'ignored' | 'fixed'>('open')
  const [open, setOpen] = useState<string | null>(null)
  const { data: issues, isLoading } = useIssues(site.id, { status, severity: severity || undefined, rule_code: rule || undefined })
  const { data: rules } = useRules()
  const update = useUpdateIssue(site.id)

  const groups = useMemo(() => {
    const m = new Map<string, Issue[]>()
    for (const i of issues ?? []) m.set(i.rule_code, [...(m.get(i.rule_code) ?? []), i])
    return [...m.entries()].sort((a, b) => SEVERITY_ORDER.indexOf(a[1][0].severity) - SEVERITY_ORDER.indexOf(b[1][0].severity) || b[1].length - a[1].length)
  }, [issues])
  const ruleOf = (code: string) => rules?.find((r) => r.code === code)
  const counts = useMemo(() => {
    const c: Partial<Record<Severity, number>> = {}
    for (const i of issues ?? []) c[i.severity] = (c[i.severity] ?? 0) + 1
    return c
  }, [issues])

  return (
    <PageMotion className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-center gap-2 px-5 py-4">
        <div className="flex rounded-lg bg-line-2 p-0.5 text-sm font-medium">
          {(['open', 'fixed', 'ignored'] as const).map((s) => (
            <button key={s} onClick={() => setStatus(s)} className={cn('relative rounded-md px-3 py-1.5 capitalize transition-colors', status === s ? 'text-ink' : 'text-ink-3 hover:text-ink')}>
              {status === s && <motion.span layoutId="issue-status" className="absolute inset-0 rounded-md bg-surface shadow-sm" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
              <span className="relative">{s}</span>
            </button>
          ))}
        </div>
        <div className="ml-2 flex items-center gap-1.5">
          {SEVERITY_ORDER.map((s) => (
            <button
              key={s}
              onClick={() => setSeverity(severity === s ? '' : s)}
              className={cn('rounded-full border px-2.5 py-1 text-xs font-medium transition-all', severity === s ? 'border-ink bg-ink text-white' : 'border-line hover:border-ink-3')}
            >
              {SEVERITY_LABEL[s]} {counts[s] ? <span className="tabular-nums opacity-70">{counts[s]}</span> : null}
            </button>
          ))}
        </div>
        {rule && (
          <Chip tone="brand" className="ml-auto">
            {ruleOf(rule)?.title ?? rule}
            <button onClick={() => setParams({})} className="ml-1 opacity-60 hover:opacity-100">
              ×
            </button>
          </Chip>
        )}
      </Card>

      {isLoading ? (
        <Card className="flex flex-col gap-3 p-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </Card>
      ) : groups.length === 0 ? (
        <Card>
          <Empty icon={<Sparkles className="size-5" />} title={status === 'open' ? 'No open issues' : `No ${status} issues`} hint="Run a crawl to audit the site." />
        </Card>
      ) : (
        groups.map(([code, list]) => {
          const r = ruleOf(code)
          return (
            <Card key={code} className="overflow-hidden">
              <div className="flex items-center gap-4 px-6 py-4">
                <SeverityDot severity={list[0].severity} className="w-[92px]" />
                <div className="flex-1">
                  <h3 className="font-semibold">{r?.title ?? code}</h3>
                  <p className="text-xs text-ink-3">
                    {r?.category} · {code}
                  </p>
                </div>
                <span className="text-lg font-medium tabular-nums">{list.length}</span>
              </div>
              {list[0].fix_hint && (
                <div className="mx-6 mb-3 flex items-start gap-2 rounded-lg bg-brand-tint px-3 py-2 text-sm">
                  <Lightbulb className="mt-0.5 size-4 shrink-0" />
                  <span>{list[0].fix_hint}</span>
                </div>
              )}
              <motion.ul variants={{ show: { transition: { staggerChildren: 0.02 } } }} initial="hidden" animate="show" className="border-t border-line">
                {list.map((i) => (
                  <motion.li key={i.id} variants={fadeUp} className="border-b border-line-2 last:border-0">
                    <button onClick={() => setOpen(open === i.id ? null : i.id)} className="row-hover flex w-full items-center gap-3 px-6 py-3 text-left text-sm">
                      <span className="w-[260px] shrink-0 truncate font-medium">{i.page_path ?? '—'}</span>
                      <span className="flex-1 truncate text-ink-2">{i.message}</span>
                      <span className="text-xs text-ink-3">{timeAgo(i.detected_at)}</span>
                      <ChevronDown className={cn('size-4 text-ink-3 transition-transform', open === i.id && 'rotate-180')} />
                    </button>
                    <AnimatePresence initial={false}>
                      {open === i.id && (
                        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                          <div className="flex items-start gap-4 bg-canvas px-6 py-4 text-sm">
                            <pre className="scroll-thin max-h-40 flex-1 overflow-auto rounded-lg bg-surface p-3 text-xs text-ink-2">{JSON.stringify(i.details, null, 2)}</pre>
                            <div className="flex flex-col gap-2">
                              {i.status === 'open' ? (
                                <Button size="sm" variant="secondary" icon={<EyeOff className="size-4" />} onClick={() => update.mutate({ id: i.id, status: 'ignored' })} loading={update.isPending}>
                                  Ignore
                                </Button>
                              ) : (
                                <Button size="sm" variant="secondary" icon={<RotateCcw className="size-4" />} onClick={() => update.mutate({ id: i.id, status: 'open' })} loading={update.isPending}>
                                  Reopen
                                </Button>
                              )}
                              {i.status === 'fixing' && (
                                <Chip tone="info">
                                  <CheckCircle2 className="size-3" /> in a change set
                                </Chip>
                              )}
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.li>
                ))}
              </motion.ul>
            </Card>
          )
        })
      )}
    </PageMotion>
  )
}

import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, ArrowRightLeft, Check, Loader2, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { useCreateMigration, useMigrations, useToggleStep } from '@/api/hooks'
import type { MigrationPlan } from '@/api/types'
import { Button } from '@/components/ui/Button'
import { Card, Chip, CountUp, Empty, PageMotion, SeverityDot, fadeUp } from '@/components/ui/primitives'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { humanize, timeAgo } from '@/lib/format'
import { useSite } from '@/lib/site'

const PHASES = ['prepare', 'stage', 'validate', 'cutover', 'monitor'] as const

export function Migration() {
  const { site } = useSite()
  const { data: plans } = useMigrations(site.id)
  const create = useCreateMigration(site.id)
  const toast = useToast()
  const [oldUrl, setOldUrl] = useState(site.url)
  const [newUrl, setNewUrl] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const plan = plans?.find((p) => p.id === selected) ?? plans?.[0] ?? null

  const submit = () =>
    create.mutate(
      { old_url: oldUrl, new_url: newUrl },
      {
        onSuccess: (p) => {
          setSelected(p.id)
          setNewUrl('')
          toast({ tone: 'success', title: 'Migration Advisor started', detail: 'Crawling both sites, then mapping every URL.' })
        },
        onError: (e) => toast({ tone: 'error', title: 'Could not start', detail: e.message }),
      },
    )

  return (
    <PageMotion className="flex flex-col gap-4">
      <Card className="p-6">
        <h2 className="text-[1.25rem] font-semibold tracking-tight">Plan a migration</h2>
        <p className="mt-1 text-sm text-ink-3">
          The Advisor crawls the old and the new site, maps every URL, lists what the new site loses, and recommends the safest path — usually a staging subdomain first.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input className="input max-w-xs" placeholder="https://old-site.com" value={oldUrl} onChange={(e) => setOldUrl(e.target.value)} />
          <ArrowRight className="size-5 text-ink-3" />
          <input className="input max-w-xs" placeholder="https://staging.new-site.com" value={newUrl} onChange={(e) => setNewUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} />
          <Button icon={<ArrowRightLeft className="size-4" />} onClick={submit} loading={create.isPending} disabled={!newUrl}>
            Compare sites
          </Button>
        </div>
      </Card>

      {plans && plans.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {plans.map((p) => (
            <button key={p.id} onClick={() => setSelected(p.id)} className={cn('rounded-full border px-3 py-1 text-xs font-medium', plan?.id === p.id ? 'border-ink bg-ink text-white' : 'border-line')}>
              {p.new_url.replace(/^https?:\/\//, '')} · {timeAgo(p.created_at)}
            </button>
          ))}
        </div>
      )}

      {!plan ? (
        <Card>
          <Empty icon={<ArrowRightLeft className="size-5" />} title="No migration plans yet" hint="Enter the new site's URL above to get a URL map, redirect list and a staged cutover plan." />
        </Card>
      ) : plan.status !== 'ready' ? (
        <Card className="flex items-center gap-4 p-6">
          {plan.status === 'failed' ? <ShieldAlert className="size-6 text-bad" /> : <Loader2 className="size-6 animate-spin" />}
          <div>
            <p className="font-medium">{plan.status === 'failed' ? 'Advisor failed' : humanize(plan.status) + '…'}</p>
            <p className="text-sm text-ink-3">{plan.error ?? `${plan.old_url} → ${plan.new_url}`}</p>
          </div>
        </Card>
      ) : (
        <PlanView plan={plan} />
      )}
    </PageMotion>
  )
}

function PlanView({ plan }: { plan: MigrationPlan }) {
  const { site } = useSite()
  const toggle = useToggleStep(site.id)
  const [tab, setTab] = useState<'steps' | 'map' | 'gaps' | 'redirects'>('steps')
  const p = plan.plan!
  const risk = p.risk_score
  const riskTone = risk >= 50 ? 'text-bad' : risk >= 20 ? 'text-warn' : 'text-good'
  const done = p.steps.filter((s) => s.done).length

  return (
    <>
      <Card className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[auto_1fr]">
        <div className="flex items-center gap-8">
          <div className="text-center">
            <div className={cn('text-[4rem] leading-none font-medium tracking-tighter tabular-nums', riskTone)}>
              <CountUp value={risk} />
            </div>
            <div className="mt-1 text-sm text-ink-3">risk / 100</div>
          </div>
          <div className="h-20 w-px bg-line" />
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <span className="text-ink-3">Old pages</span>
            <span className="font-medium tabular-nums">{p.stats.old_pages}</span>
            <span className="text-ink-3">Mapped</span>
            <span className="font-medium tabular-nums">{p.stats.mapped}</span>
            <span className="text-ink-3">Unmapped</span>
            <span className={cn('font-medium tabular-nums', p.stats.unmapped > 0 && 'text-bad')}>{p.stats.unmapped}</span>
            <span className="text-ink-3">Traffic covered</span>
            <span className="font-medium tabular-nums">{p.stats.old_traffic_covered == null ? '—' : `${Math.round(p.stats.old_traffic_covered * 100)}%`}</span>
          </div>
        </div>
        <div>
          <Chip tone={p.strategy === 'staged_subdomain' ? 'brand' : 'good'} className="mb-2">
            Recommended: {p.strategy === 'staged_subdomain' ? 'stage on a subdomain first' : 'direct cutover is acceptable'}
          </Chip>
          <p className="text-sm leading-relaxed">{p.summary}</p>
          {p.narrative && (
            <div className="mt-3 rounded-lg bg-brand-tint px-4 py-3 text-sm">
              <p>{p.narrative.executive_summary}</p>
              <ul className="mt-2 list-disc pl-5 text-ink-2">
                {p.narrative.top_risks.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              <p className="mt-2 font-medium">{p.narrative.go_no_go}</p>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <div className="flex items-center gap-2 border-b border-line px-6 py-3">
          {(['steps', 'gaps', 'map', 'redirects'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={cn('relative rounded-md px-3 py-1.5 text-sm font-medium capitalize', tab === t ? 'text-ink' : 'text-ink-3 hover:text-ink')}>
              {tab === t && <motion.span layoutId="mig-tab" className="absolute inset-0 rounded-md bg-line-2" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
              <span className="relative">
                {t} {t === 'gaps' ? `(${p.gaps.length})` : t === 'redirects' ? `(${p.redirects.length})` : t === 'steps' ? `${done}/${p.steps.length}` : ''}
              </span>
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={tab} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} className="p-6">
            {tab === 'steps' && (
              <ol className="flex flex-col gap-6">
                {PHASES.map((phase) => {
                  const steps = p.steps.filter((s) => s.phase === phase)
                  if (!steps.length) return null
                  return (
                    <li key={phase}>
                      <div className="mb-2 text-xs font-semibold tracking-wide text-ink-3 uppercase">{phase}</div>
                      <ul className="flex flex-col gap-2">
                        {steps.map((s) => (
                          <motion.li key={s.order} variants={fadeUp} initial="hidden" animate="show" className="flex items-start gap-3">
                            <button
                              onClick={() => toggle.mutate({ planId: plan.id, order: s.order, done: !s.done })}
                              className={cn('mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border transition-all', s.done ? 'border-good bg-good text-white' : 'border-line hover:border-ink')}
                              aria-label={s.done ? 'Mark not done' : 'Mark done'}
                            >
                              <AnimatePresence>{s.done && <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}><Check className="size-3.5" strokeWidth={3} /></motion.span>}</AnimatePresence>
                            </button>
                            <div>
                              <p className={cn('font-medium', s.done && 'text-ink-3 line-through')}>
                                {s.order}. {s.title}
                              </p>
                              <p className="text-sm text-ink-2">{s.detail}</p>
                            </div>
                          </motion.li>
                        ))}
                      </ul>
                    </li>
                  )
                })}
              </ol>
            )}
            {tab === 'gaps' && (
              <ul className="flex flex-col divide-y divide-line-2">
                {p.gaps.length === 0 && <p className="text-sm text-ink-3">No gaps — the new site carries everything over.</p>}
                {p.gaps.map((g, i) => (
                  <li key={i} className="flex items-start gap-4 py-3 text-sm">
                    <SeverityDot severity={g.severity} className="w-[92px] shrink-0" />
                    <span className="w-56 shrink-0 truncate font-medium">{g.path}</span>
                    <Chip tone="neutral">{humanize(g.kind)}</Chip>
                    <span className="text-ink-2">{g.detail}</span>
                  </li>
                ))}
              </ul>
            )}
            {tab === 'map' && (
              <table className="w-full text-sm">
                <thead className="text-left text-xs font-semibold tracking-wide text-ink-3 uppercase">
                  <tr>
                    <th className="pb-2">Old path</th>
                    <th className="pb-2">New path</th>
                    <th className="pb-2">Method</th>
                    <th className="pb-2 text-right">Confidence</th>
                    <th className="pb-2 text-right">Clicks · 90d</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-2">
                  {p.url_map.map((m) => (
                    <tr key={m.old_path}>
                      <td className="py-2 font-medium">{m.old_path}</td>
                      <td className={cn('py-2', !m.new_path && 'text-bad')}>{m.new_path ?? 'no target'}</td>
                      <td className="py-2 text-ink-3">{m.method}</td>
                      <td className="py-2 text-right tabular-nums">{m.new_path ? `${Math.round(m.confidence * 100)}%` : '—'}</td>
                      <td className="py-2 text-right tabular-nums">{m.clicks}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {tab === 'redirects' && (
              <pre className="scroll-thin max-h-[480px] overflow-auto rounded-lg bg-canvas p-4 font-mono text-xs leading-6">
                {p.redirects.map((r) => `${r.from}  ->  ${r.to}  [${r.code}]`).join('\n') || '# no redirects needed'}
              </pre>
            )}
          </motion.div>
        </AnimatePresence>
      </Card>
    </>
  )
}

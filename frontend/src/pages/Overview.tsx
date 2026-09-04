import { motion } from 'framer-motion'
import { ChevronRight, Sparkles, TrendingDown } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router'
import { useIssues, useOverview, useRules, useTrend } from '@/api/hooks'
import type { Severity } from '@/api/types'
import { ScoreRing } from '@/components/charts/ScoreRing'
import { TrendChart } from '@/components/charts/TrendChart'
import { Card, CardHeader, CountUp, Empty, PageMotion, SeverityDot, Skeleton, ViewAll, fadeUp } from '@/components/ui/primitives'
import { cn } from '@/lib/cn'
import { SEVERITY_ORDER, fmt, healthLabel, timeAgo } from '@/lib/format'
import { useSite } from '@/lib/site'

const toneText = { good: 'text-good', warn: 'text-warn', bad: 'text-bad', muted: 'text-ink-3' }

export function Overview() {
  const { site } = useSite()
  const { data: ov, isLoading } = useOverview(site.id)
  const { data: trend } = useTrend(site.id, 35)
  const { data: issues } = useIssues(site.id, { status: 'open' })
  const { data: rules } = useRules()

  const groups = useMemo(() => {
    if (!issues) return []
    const byCode = new Map<string, { code: string; severity: Severity; count: number }>()
    for (const i of issues) {
      const g = byCode.get(i.rule_code) ?? { code: i.rule_code, severity: i.severity, count: 0 }
      g.count++
      byCode.set(i.rule_code, g)
    }
    return [...byCode.values()].sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) || b.count - a.count).slice(0, 5)
  }, [issues])
  const ruleTitle = (code: string) => rules?.find((r) => r.code === code)?.title ?? code

  const health = healthLabel(ov?.site_score ?? null)

  return (
    <PageMotion className="flex flex-col gap-4">
      {/* ---------- site health ---------- */}
      <Card className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1.15fr_1fr]">
        <div>
          <h2 className="text-[1.25rem] font-semibold tracking-tight">Site health</h2>
          {isLoading ? (
            <div className="flex items-center gap-10 py-10 pl-8">
              <Skeleton className="size-[190px] rounded-full" />
              <Skeleton className="h-6 w-24" />
            </div>
          ) : (
            <div className="flex items-center gap-10 py-6 pl-4">
              <div className="relative grid place-items-center">
                <ScoreRing score={ov?.site_score ?? null} />
                <div className="absolute text-[5.6rem] leading-none font-medium tracking-tighter tabular-nums">{ov?.site_score != null ? <CountUp value={ov.site_score} /> : '—'}</div>
              </div>
              <div className="h-28 w-px bg-line" />
              <div className="flex flex-col gap-3">
                <div className={cn('flex items-center gap-2.5 text-[1.35rem] font-medium', toneText[health.tone])}>
                  <span className={cn('size-3 rounded-full bg-current', health.tone === 'good' && 'pulse-dot')} />
                  {health.label}
                </div>
                <dl className="grid grid-cols-[auto_auto] gap-x-6 gap-y-1.5 text-sm">
                  <dt className="text-ink-3">Pages</dt>
                  <dd className="font-medium tabular-nums">{fmt(ov?.pages)}</dd>
                  <dt className="text-ink-3">Open issues</dt>
                  <dd className="font-medium tabular-nums">{fmt(ov?.open_issues)}</dd>
                  <dt className="text-ink-3">Clicks · 28d</dt>
                  <dd className="font-medium tabular-nums">{fmt(ov?.clicks_28d)}</dd>
                  <dt className="text-ink-3">Last crawl</dt>
                  <dd className="font-medium">{ov?.last_crawl ? timeAgo(ov.last_crawl.finished_at ?? ov.last_crawl.created_at) : 'never'}</dd>
                </dl>
              </div>
            </div>
          )}
        </div>

        <Link to="/changes" className="group block">
          <motion.div
            whileHover={{ y: -2 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className="relative flex h-full min-h-[270px] items-center overflow-hidden rounded-xl bg-brand-tint px-10 transition-shadow group-hover:shadow-[0_16px_40px_-20px_rgb(230_179_0/0.6)]"
          >
            <div className="pointer-events-none absolute -top-20 -right-20 size-56 rounded-full bg-brand/25 blur-3xl transition-transform duration-700 group-hover:scale-125" />
            <div className="flex flex-1 flex-col gap-1">
              <div className="text-[4.2rem] leading-none font-medium tracking-tighter tabular-nums">{ov ? <CountUp value={ov.pending_change_sets} /> : '—'}</div>
              <div className="text-[1.25rem] text-ink-2">pending</div>
              <div className="mt-2 text-sm text-ink-3">change set{ov?.pending_change_sets === 1 ? '' : 's'} waiting for your approval</div>
            </div>
            <div className="mx-8 h-28 w-px bg-ink/10" />
            <div className="flex items-center gap-2 text-[1.15rem] font-medium">
              View all
              <ChevronRight className="size-5 transition-transform duration-300 group-hover:translate-x-1.5" />
            </div>
          </motion.div>
        </Link>
      </Card>

      {/* ---------- keywords + issues ---------- */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr]">
        <Card className="pb-4">
          <CardHeader title="Keywords" action={<ViewAll to="/keywords" />} />
          <div className="px-6">
            {trend ? <TrendChart data={trend} /> : <Skeleton className="h-[260px]" />}
          </div>
          {ov && ov.recent_drops.length > 0 && (
            <motion.div variants={fadeUp} className="mx-6 mt-4 flex items-start gap-2 rounded-lg bg-bad-tint px-3 py-2 text-sm text-bad">
              <TrendingDown className="mt-0.5 size-4 shrink-0" />
              <span>
                {ov.recent_drops.length} keyword{ov.recent_drops.length > 1 ? 's' : ''} dropped this week — <Link to="/keywords?view=drops" className="underline">review</Link>
              </span>
            </motion.div>
          )}
        </Card>

        <Card>
          <CardHeader title="Issues" action={<ViewAll to="/issues" />} />
          <div className="px-6 pb-2">
            <div className="h-px bg-line" />
            {!issues ? (
              <div className="flex flex-col gap-4 py-4">
                {[0, 1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : groups.length === 0 ? (
              <Empty icon={<Sparkles className="size-5" />} title="No open issues" hint={ov?.pages ? 'Everything the Auditor checks is passing.' : 'Run a crawl to audit the site.'} />
            ) : (
              <motion.ul variants={{ show: { transition: { staggerChildren: 0.05 } } }} initial="hidden" animate="show">
                {groups.map((g) => (
                  <motion.li key={g.code} variants={fadeUp}>
                    <Link to={`/issues?rule=${g.code}`} className="row-hover -mx-3 flex items-center gap-4 rounded-lg px-3 py-5">
                      <SeverityDot severity={g.severity} className="w-[92px] shrink-0 text-[0.95rem]" />
                      <span className="flex-1 text-[0.95rem]">{ruleTitle(g.code)}</span>
                      <span className="text-[1.05rem] font-medium tabular-nums">{g.count}</span>
                      <ChevronRight className="row-chevron size-5" />
                    </Link>
                    <div className="h-px bg-line-2" />
                  </motion.li>
                ))}
              </motion.ul>
            )}
          </div>
        </Card>
      </div>
    </PageMotion>
  )
}

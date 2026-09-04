import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, Bot, Check, ExternalLink, FileText, GitBranch, GitPullRequest, Pencil, ShieldCheck, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useChangeSet, useChangeSetAction, useChangeSets, useDropChange, useEditChange } from '@/api/hooks'
import type { Change, ChangeSet, ChangeSetStatus } from '@/api/types'
import { Button } from '@/components/ui/Button'
import { Card, Chip, Empty, PageMotion, Skeleton, fadeUp } from '@/components/ui/primitives'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { STATUS_LABEL, humanize, timeAgo } from '@/lib/format'
import { useSite } from '@/lib/site'

const TONE: Record<ChangeSetStatus, 'brand' | 'good' | 'warn' | 'bad' | 'info' | 'neutral'> = {
  pending_approval: 'brand',
  approved: 'info',
  rejected: 'neutral',
  awaiting_manual: 'warn',
  branch_ready: 'info',
  pr_opened: 'info',
  merged: 'info',
  verified: 'good',
  failed: 'bad',
  rolled_back: 'bad',
}

export function StatusChip({ status }: { status: ChangeSetStatus }) {
  return (
    <Chip tone={TONE[status]}>
      {status === 'verified' && <ShieldCheck className="size-3" />}
      {status === 'pr_opened' && <GitPullRequest className="size-3" />}
      {STATUS_LABEL[status] ?? humanize(status)}
    </Chip>
  )
}

export function Changes() {
  const { site } = useSite()
  const { data: sets, isLoading } = useChangeSets(site.id)
  const [tab, setTab] = useState<'inbox' | 'all'>('inbox')
  const visible = sets?.filter((s) => (tab === 'inbox' ? ['pending_approval', 'awaiting_manual', 'branch_ready', 'pr_opened', 'failed'].includes(s.status) : true)) ?? []

  return (
    <PageMotion className="flex flex-col gap-4">
      <Card className="flex items-center gap-3 px-5 py-4">
        <div className="flex rounded-lg bg-line-2 p-0.5 text-sm font-medium">
          {(['inbox', 'all'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={cn('relative rounded-md px-3 py-1.5 capitalize', tab === t ? 'text-ink' : 'text-ink-3 hover:text-ink')}>
              {tab === t && <motion.span layoutId="cs-tab" className="absolute inset-0 rounded-md bg-surface shadow-sm" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
              <span className="relative">{t === 'inbox' ? 'Needs you' : 'All'}</span>
            </button>
          ))}
        </div>
        <p className="ml-2 text-sm text-ink-3">The Fixer drafts; nothing ships until you approve it here.</p>
      </Card>

      {isLoading ? (
        <Card className="flex flex-col gap-3 p-6">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </Card>
      ) : visible.length === 0 ? (
        <Card>
          <Empty icon={<FileText className="size-5" />} title={tab === 'inbox' ? 'Nothing waiting on you' : 'No change sets yet'} hint="After a crawl, the Fixer proposes edits for the highest-value issues." />
        </Card>
      ) : (
        <motion.div variants={{ show: { transition: { staggerChildren: 0.05 } } }} initial="hidden" animate="show" className="flex flex-col gap-3">
          {visible.map((cs) => (
            <ChangeSetRow key={cs.id} cs={cs} />
          ))}
        </motion.div>
      )}
    </PageMotion>
  )
}

function ChangeSetRow({ cs }: { cs: ChangeSet }) {
  return (
    <motion.div variants={fadeUp}>
      <Link to={`/changes/${cs.id}`} className="card card-hover flex items-center gap-5 px-6 py-5">
        <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand-tint">
          <Bot className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate font-semibold">{cs.title}</h3>
            <StatusChip status={cs.status} />
          </div>
          <p className="mt-0.5 truncate text-sm text-ink-3">
            {cs.summary} · {timeAgo(cs.created_at)}
            {cs.pr_number ? ` · PR #${cs.pr_number}` : ''}
          </p>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold tabular-nums">+{cs.expected_impact}</div>
          <div className="text-xs text-ink-3">expected score</div>
        </div>
      </Link>
    </motion.div>
  )
}

// ---------- detail ----------
export function ChangeSetDetail() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const { site } = useSite()
  const { data: cs, isLoading } = useChangeSet(id)
  const act = useChangeSetAction(site.id)
  const toast = useToast()
  const [done, setDone] = useState<'approve' | 'reject' | null>(null)
  const [note, setNote] = useState('')

  const run = (action: 'approve' | 'reject' | 'mark-applied' | 'verify') =>
    act.mutate(
      { id, action, note: note || undefined },
      {
        onSuccess: (d) => {
          if (action === 'approve' || action === 'reject') {
            setDone(action)
            setTimeout(() => setDone(null), 1800)
          }
          toast({
            tone: action === 'reject' ? 'info' : 'success',
            title: action === 'approve' ? 'Approved — publishing' : action === 'reject' ? 'Rejected' : action === 'mark-applied' ? 'Marked applied — verifying' : 'Verification queued',
            detail: action === 'approve' ? (d.status === 'approved' ? 'The Fixer is opening the branch/PR now.' : undefined) : undefined,
          })
        },
        onError: (e) => toast({ tone: 'error', title: 'Action failed', detail: e.message }),
      },
    )

  if (isLoading || !cs)
    return (
      <Card className="p-6">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="mt-4 h-40" />
      </Card>
    )

  const pending = cs.status === 'pending_approval'
  const verified = cs.changes.filter((c) => c.apply_status === 'verified').length
  const failed = cs.changes.filter((c) => c.apply_status === 'failed').length

  return (
    <PageMotion className="flex flex-col gap-4">
      <button onClick={() => nav('/changes')} className="link-arrow w-fit text-sm text-ink-3">
        <ArrowLeft className="size-4" /> All changes
      </button>

      <Card className="p-6">
        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-semibold tracking-tight">{cs.title}</h2>
              <StatusChip status={cs.status} />
            </div>
            <p className="mt-1 text-sm text-ink-3">
              {cs.summary} · proposed by the {humanize(cs.created_by_agent)} {timeAgo(cs.created_at)} · expected +{cs.expected_impact} score
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              {cs.branch && (
                <Chip>
                  <GitBranch className="size-3" /> {cs.branch}
                </Chip>
              )}
              {cs.pr_url && (
                <a href={cs.pr_url} target="_blank" rel="noreferrer" className="link-arrow text-info">
                  <GitPullRequest className="size-4" /> PR #{cs.pr_number} <ExternalLink className="size-3" />
                </a>
              )}
              {cs.decision_note && <span className="text-ink-3">“{cs.decision_note}”</span>}
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            {pending && (
              <>
                <input className="input w-44" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                <Button variant="danger" icon={<X className="size-4" />} onClick={() => run('reject')} loading={act.isPending && act.variables?.action === 'reject'} success={done === 'reject'}>
                  Reject
                </Button>
                <Button icon={<Check className="size-4" strokeWidth={2.5} />} onClick={() => run('approve')} loading={act.isPending && act.variables?.action === 'approve'} success={done === 'approve'}>
                  Approve &amp; publish
                </Button>
              </>
            )}
            {['awaiting_manual', 'branch_ready', 'pr_opened', 'approved'].includes(cs.status) && (
              <Button icon={<Check className="size-4" />} onClick={() => run('mark-applied')} loading={act.isPending}>
                Mark applied
              </Button>
            )}
            {['merged', 'verified', 'failed'].includes(cs.status) && (
              <Button variant="secondary" icon={<ShieldCheck className="size-4" />} onClick={() => run('verify')} loading={act.isPending}>
                Re-verify
              </Button>
            )}
          </div>
        </div>

        {cs.status === 'awaiting_manual' && (
          <div className="mt-4 rounded-lg bg-warn-tint px-4 py-3 text-sm">
            No repository is connected, so these edits were not applied automatically. Make them by hand, then press <b>Mark applied</b> — the Verifier will re-crawl and confirm.
          </div>
        )}
        {(cs.status === 'verified' || cs.status === 'failed') && (
          <div className={cn('mt-4 rounded-lg px-4 py-3 text-sm', cs.status === 'verified' ? 'bg-good-tint' : 'bg-bad-tint')}>
            Verifier re-crawled the pages: <b>{verified}</b> fix{verified === 1 ? '' : 'es'} confirmed live{failed ? `, ${failed} still reported by the audit` : ''}.
          </div>
        )}
      </Card>

      <motion.div variants={{ show: { transition: { staggerChildren: 0.05 } } }} initial="hidden" animate="show" className="flex flex-col gap-3">
        {cs.changes.map((c) => (
          <ChangeCard key={c.id} change={c} editable={pending} changeSetId={cs.id} />
        ))}
      </motion.div>
    </PageMotion>
  )
}

function ChangeCard({ change: c, editable, changeSetId }: { change: Change; editable: boolean; changeSetId: string }) {
  const edit = useEditChange(changeSetId)
  const drop = useDropChange(changeSetId)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(c.after)
  useEffect(() => setValue(c.after), [c.after])
  const applyTone = { pending: 'neutral', applied: 'info', needs_manual: 'warn', verified: 'good', failed: 'bad' } as const

  return (
    <motion.div variants={fadeUp} layout className="card p-5">
      <div className="flex items-center gap-3">
        <Chip tone="neutral">{humanize(c.kind)}</Chip>
        <span className="truncate font-medium">{c.page_path ?? '—'}</span>
        <span className="ml-auto flex items-center gap-2 text-xs">
          <span className="text-ink-3">{c.generated_by === 'llm' ? 'written by AI' : c.generated_by === 'user' ? 'edited by you' : 'heuristic draft'}</span>
          {c.apply_status !== 'pending' && <Chip tone={applyTone[c.apply_status]}>{humanize(c.apply_status)}</Chip>}
        </span>
        {editable && (
          <div className="flex items-center gap-1">
            <button className="btn btn-ghost btn-icon" aria-label="Edit" onClick={() => setEditing((v) => !v)}>
              <Pencil className="size-4" />
            </button>
            <button className="btn btn-ghost btn-icon text-bad" aria-label="Remove" onClick={() => drop.mutate(c.id)}>
              <Trash2 className="size-4" />
            </button>
          </div>
        )}
      </div>
      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        <div className="rounded-lg border border-bad/20 bg-bad-tint/60 px-3 py-2 text-sm">
          <div className="mb-1 text-[10px] font-semibold tracking-wide text-bad uppercase">Before</div>
          <div className={cn('text-ink-2', !c.before && 'italic')}>{c.before || 'empty'}</div>
        </div>
        <div className="rounded-lg border border-good/20 bg-good-tint/70 px-3 py-2 text-sm">
          <div className="mb-1 text-[10px] font-semibold tracking-wide text-good uppercase">After</div>
          <AnimatePresence mode="wait" initial={false}>
            {editing ? (
              <motion.div key="edit" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col gap-2">
                <textarea className="input min-h-[64px] bg-surface" value={value} onChange={(e) => setValue(e.target.value)} />
                <div className="flex justify-end gap-2">
                  <span className="mr-auto self-center text-xs text-ink-3 tabular-nums">{value.length} chars</span>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => edit.mutate({ id: c.id, after: value }, { onSuccess: () => setEditing(false) })}
                    loading={edit.isPending}
                  >
                    Save
                  </Button>
                </div>
              </motion.div>
            ) : (
              <motion.div key="view" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                {c.after}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
      <p className="mt-2 text-xs text-ink-3">{c.rationale}</p>
      {c.apply_note && <p className="mt-1 text-xs text-warn">{c.apply_note}</p>}
      {c.file_path && <p className="mt-1 font-mono text-xs text-ink-3">{c.file_path}</p>}
    </motion.div>
  )
}

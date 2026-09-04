import { motion } from 'framer-motion'
import { Bot, Check, Cloud, GitBranch, GitPullRequest, Globe, Plus, Save, Wifi } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useCreateSite, useJobs, useOverview, useRetryJob, useUpdateSite } from '@/api/hooks'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader, Chip, PageMotion, fadeUp } from '@/components/ui/primitives'
import { useToast } from '@/components/ui/Toast'
import { cn } from '@/lib/cn'
import { humanize, timeAgo } from '@/lib/format'
import { useSite } from '@/lib/site'

export function Settings() {
  const { site, select } = useSite()
  const [params] = useSearchParams()
  const { data: ov } = useOverview(site.id)
  const { data: jobs } = useJobs(site.id)
  const update = useUpdateSite(site.id)
  const create = useCreateSite()
  const retry = useRetryJob(site.id)
  const toast = useToast()
  const [saved, setSaved] = useState(false)
  const [form, setForm] = useState({
    name: site.name,
    repo: site.repo ?? '',
    default_branch: site.default_branch,
    gsc_property: site.gsc_property ?? '',
    rank_drop_threshold: site.settings.rank_drop_threshold ?? 3,
    exclude_paths: (site.settings.exclude_paths ?? []).join(', '),
    crawl_interval_hours: site.settings.schedule?.crawl_interval_hours ?? 168,
    rank_sync_interval_hours: site.settings.schedule?.rank_sync_interval_hours ?? 24,
  })
  const [newSite, setNewSite] = useState({ name: '', url: '' })
  const [showAdd, setShowAdd] = useState(params.get('add') === '1')

  const save = () =>
    update.mutate(
      {
        name: form.name,
        repo: form.repo || null,
        default_branch: form.default_branch,
        gsc_property: form.gsc_property || null,
        settings: {
          rank_drop_threshold: Number(form.rank_drop_threshold),
          exclude_paths: form.exclude_paths.split(',').map((s) => s.trim()).filter(Boolean),
          schedule: { crawl_interval_hours: Number(form.crawl_interval_hours), rank_sync_interval_hours: Number(form.rank_sync_interval_hours) },
        },
      },
      {
        onSuccess: () => {
          setSaved(true)
          setTimeout(() => setSaved(false), 1500)
          toast({ tone: 'success', title: 'Settings saved' })
        },
        onError: (e) => toast({ tone: 'error', title: 'Save failed', detail: e.message }),
      },
    )

  const integrations = [
    { key: 'network', label: 'Outbound network', icon: Wifi, hint: 'NETWORK_ENABLED in backend/.env — nothing leaves the machine until this is on' },
    { key: 'gsc', label: 'Google Search Console', icon: Cloud, hint: 'GSC_SERVICE_ACCOUNT_JSON + the property below' },
    { key: 'llm', label: 'OpenAI (copywriting & strategy)', icon: Bot, hint: 'OPENAI_API_KEY + OPENAI_MODEL — without it, fixes are heuristic drafts' },
    { key: 'repo', label: 'Local repository', icon: GitBranch, hint: 'REPO_LOCAL_PATH — where the Fixer commits' },
    { key: 'github', label: 'GitHub pull requests', icon: GitPullRequest, hint: 'GITHUB_TOKEN + the repo below' },
  ] as const

  return (
    <PageMotion className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader title="Site" />
          <div className="grid grid-cols-1 gap-4 px-6 pb-6 md:grid-cols-2">
            <Field label="Name">
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="URL">
              <input className="input" value={site.url} disabled />
            </Field>
            <Field label="Search Console property" hint='e.g. sc-domain:example.com or https://example.com/'>
              <input className="input" value={form.gsc_property} onChange={(e) => setForm({ ...form, gsc_property: e.target.value })} placeholder="sc-domain:example.com" />
            </Field>
            <Field label="Exclude paths" hint="comma-separated prefixes the crawler skips">
              <input className="input" value={form.exclude_paths} onChange={(e) => setForm({ ...form, exclude_paths: e.target.value })} placeholder="/admin, /cart" />
            </Field>
            <Field label="GitHub repo" hint="owner/name">
              <input className="input" value={form.repo} onChange={(e) => setForm({ ...form, repo: e.target.value })} placeholder="acme/website" />
            </Field>
            <Field label="Default branch">
              <input className="input" value={form.default_branch} onChange={(e) => setForm({ ...form, default_branch: e.target.value })} />
            </Field>
            <Field label="Alert when a keyword drops by" hint="positions, comparing the last 7 days to the 3 weeks before">
              <input className="input" type="number" min={1} value={form.rank_drop_threshold} onChange={(e) => setForm({ ...form, rank_drop_threshold: Number(e.target.value) })} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Crawl every (h)">
                <input className="input" type="number" min={0} value={form.crawl_interval_hours} onChange={(e) => setForm({ ...form, crawl_interval_hours: Number(e.target.value) })} />
              </Field>
              <Field label="Rank sync every (h)">
                <input className="input" type="number" min={0} value={form.rank_sync_interval_hours} onChange={(e) => setForm({ ...form, rank_sync_interval_hours: Number(e.target.value) })} />
              </Field>
            </div>
          </div>
          <div className="flex justify-end border-t border-line px-6 py-4">
            <Button icon={<Save className="size-4" />} onClick={save} loading={update.isPending} success={saved}>
              Save changes
            </Button>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Sites"
            action={
              <Button size="sm" variant="secondary" icon={<Plus className="size-4" />} onClick={() => setShowAdd((v) => !v)}>
                Add site
              </Button>
            }
          />
          {showAdd && (
            <motion.div variants={fadeUp} initial="hidden" animate="show" className="mx-6 mb-6 flex flex-wrap items-end gap-3 rounded-xl bg-brand-tint/60 p-4">
              <Field label="Name" className="min-w-[180px] flex-1">
                <input className="input" value={newSite.name} onChange={(e) => setNewSite({ ...newSite, name: e.target.value })} placeholder="My shop" />
              </Field>
              <Field label="URL" className="min-w-[240px] flex-1">
                <input className="input" value={newSite.url} onChange={(e) => setNewSite({ ...newSite, url: e.target.value })} placeholder="https://example.com" />
              </Field>
              <Button
                onClick={() =>
                  create.mutate(newSite, {
                    onSuccess: (s) => {
                      select(s.id)
                      setShowAdd(false)
                      setNewSite({ name: '', url: '' })
                      toast({ tone: 'success', title: `${s.name} added`, detail: 'Run a crawl to get the first audit.' })
                    },
                    onError: (e) => toast({ tone: 'error', title: 'Could not add site', detail: e.message }),
                  })
                }
                loading={create.isPending}
                disabled={!newSite.name || !newSite.url}
              >
                Create
              </Button>
            </motion.div>
          )}
        </Card>
      </div>

      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader title="Integrations" />
          <ul className="flex flex-col gap-1 px-6 pb-6">
            {integrations.map(({ key, label, icon: Icon, hint }) => {
              const on = ov?.integrations[key] ?? false
              return (
                <li key={key} className="flex items-start gap-3 rounded-lg px-2 py-2.5">
                  <span className={cn('mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg', on ? 'bg-good-tint text-good' : 'bg-line-2 text-ink-3')}>
                    <Icon className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{label}</span>
                      <Chip tone={on ? 'good' : 'neutral'}>{on ? <><Check className="size-3" /> on</> : 'off'}</Chip>
                    </div>
                    <p className="text-xs text-ink-3">{hint}</p>
                  </div>
                </li>
              )
            })}
          </ul>
        </Card>

        <Card>
          <CardHeader title="Recent jobs" />
          <ul className="flex flex-col divide-y divide-line-2 px-6 pb-4">
            {(jobs ?? []).slice(0, 10).map((j) => (
              <li key={j.id} className="flex items-center gap-3 py-2.5 text-sm">
                <span
                  className={cn(
                    'size-2 shrink-0 rounded-full',
                    j.status === 'done' ? 'bg-good' : j.status === 'failed' ? 'bg-bad' : j.status === 'running' ? 'pulse-dot bg-brand text-brand' : 'bg-ink-3',
                  )}
                />
                <span className="w-32 shrink-0 font-medium">{j.type}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-ink-3">{j.error ? j.error.split('\n')[0] : humanize(j.status)}</span>
                <span className="text-xs text-ink-3">{timeAgo(j.created_at)}</span>
                {j.status === 'failed' && (
                  <Button size="sm" variant="ghost" onClick={() => retry.mutate(j.id)}>
                    Retry
                  </Button>
                )}
              </li>
            ))}
            {!jobs?.length && <li className="py-6 text-center text-sm text-ink-3">No jobs yet.</li>}
          </ul>
        </Card>

        <Card className="p-5 text-sm text-ink-2">
          <div className="flex items-center gap-2 font-medium text-ink">
            <Globe className="size-4" /> Backend
          </div>
          <p className="mt-1 text-xs">Integrations are configured in <code className="rounded bg-line-2 px-1">backend/.env</code>; restart the API after editing it. This panel reflects what the server reports.</p>
        </Card>
      </div>
    </PageMotion>
  )
}

function Field({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn('flex flex-col gap-1.5', className)}>
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-ink-3">{hint}</span>}
    </label>
  )
}

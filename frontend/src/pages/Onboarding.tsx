import { motion } from 'framer-motion'
import { ArrowRight, ArrowRightLeft, Globe } from 'lucide-react'
import { useState } from 'react'
import { useCreateSite } from '@/api/hooks'
import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'

export const COMPANY = 'DesertSound'
export const CURRENT_SITE = 'https://desertsound.com.pk'

const ease = [0.16, 1, 0.3, 1] as const

/**
 * First run for DesertSound: confirm the live site and register the new website it is moving to.
 * Nothing is fetched here — crawling and the migration comparison start from the dashboard.
 */
export function Onboarding() {
  const create = useCreateSite()
  const toast = useToast()
  const [current, setCurrent] = useState(CURRENT_SITE)
  const [next, setNext] = useState('')
  const [error, setError] = useState<string | null>(null)

  const valid = (u: string) => /^https?:\/\/[^\s/]+\.[^\s/]+/i.test(u.trim())

  const submit = () => {
    if (!valid(current)) return setError('Enter the current website as a full URL, e.g. https://desertsound.com.pk')
    if (next && !valid(next)) return setError('The new website must be a full URL, e.g. https://new.desertsound.com.pk')
    setError(null)
    create.mutate(
      { name: COMPANY, url: current.trim(), settings: { company: COMPANY, new_site_url: next.trim() || null } },
      { onError: (e) => toast({ tone: 'error', title: 'Could not set up the site', detail: e.message }) },
    )
  }

  return (
    <div className="grid h-full place-items-center bg-canvas p-6">
      <motion.div initial={{ opacity: 0, y: 14, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5, ease }} className="card w-full max-w-lg overflow-hidden">
        <div className="flex items-center gap-4 border-b border-line bg-brand-tint/60 px-8 py-6">
          <img src="/favicon.png" alt="" className="size-12" />
          <div>
            <div className="text-[1.35rem] font-bold tracking-tight">SEO Engine</div>
            <div className="text-sm text-ink-2">for {COMPANY}</div>
          </div>
        </div>

        <div className="px-8 py-7">
          <h1 className="text-2xl font-semibold tracking-tight">Let's set up {COMPANY}</h1>
          <p className="mt-1 text-sm text-ink-3">Confirm the live site and add the new website it's moving to. Seven agents will audit, fix and track both.</p>

          <motion.div initial="hidden" animate="show" variants={{ show: { transition: { staggerChildren: 0.08, delayChildren: 0.15 } } }} className="mt-7 flex flex-col gap-5">
            <Field icon={<Globe className="size-4" />} label="Current website" hint="The site that ranks today. It gets crawled, scored and tracked.">
              <input className="input" value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="https://desertsound.com.pk" />
            </Field>
            <Field icon={<ArrowRightLeft className="size-4" />} label="New website" hint="Where DesertSound is moving to (staging or live). The Migration Advisor will map every URL from the current site to it. You can add this later in Settings.">
              <input className="input" value={next} onChange={(e) => setNext(e.target.value)} placeholder="https://new.desertsound.com.pk" onKeyDown={(e) => e.key === 'Enter' && submit()} />
            </Field>
          </motion.div>

          {error && (
            <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="mt-4 rounded-lg bg-bad-tint px-3 py-2 text-sm text-bad">
              {error}
            </motion.p>
          )}

          <Button className="mt-7 w-full" iconRight={<ArrowRight className="size-4" />} disabled={!current} loading={create.isPending} onClick={submit}>
            Open the dashboard
          </Button>
          <p className="mt-3 text-center text-xs text-ink-3">No crawling starts until you press <b>Run crawl</b>.</p>
        </div>
      </motion.div>
    </div>
  )
}

function Field({ icon, label, hint, children }: { icon: React.ReactNode; label: string; hint: string; children: React.ReactNode }) {
  return (
    <motion.label variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: { duration: 0.4, ease } } }} className="flex flex-col gap-1.5">
      <span className="flex items-center gap-2 text-sm font-medium">
        <span className="grid size-6 place-items-center rounded-md bg-brand-tint text-ink">{icon}</span>
        {label}
      </span>
      {children}
      <span className="text-xs text-ink-3">{hint}</span>
    </motion.label>
  )
}

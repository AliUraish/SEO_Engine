import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import { useState } from 'react'
import { useCreateSite } from '@/api/hooks'
import { Button } from '@/components/ui/Button'
import { useToast } from '@/components/ui/Toast'

export function Onboarding() {
  const create = useCreateSite()
  const toast = useToast()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')

  return (
    <div className="grid h-full place-items-center bg-canvas p-6">
      <motion.div initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }} className="card w-full max-w-md p-8">
        <div className="text-[1.45rem] font-bold tracking-tight">SEO Engine</div>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">Add your first site</h1>
        <p className="mt-1 text-sm text-ink-3">Seven agents will crawl it, score it, and propose fixes for you to approve.</p>
        <div className="mt-6 flex flex-col gap-4">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Name
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="My shop" autoFocus />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            URL
            <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com" />
          </label>
          <Button
            className="mt-2 w-full"
            iconRight={<ArrowRight className="size-4" />}
            disabled={!name || !url}
            loading={create.isPending}
            onClick={() => create.mutate({ name, url }, { onError: (e) => toast({ tone: 'error', title: 'Could not add site', detail: e.message }) })}
          >
            Continue
          </Button>
        </div>
      </motion.div>
    </div>
  )
}

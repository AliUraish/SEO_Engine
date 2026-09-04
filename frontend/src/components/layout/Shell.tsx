import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { useLocation, useOutlet } from 'react-router'
import { useOverview } from '@/api/hooks'
import { useSite } from '@/lib/site'
import { ActivityDrawer, useLiveEvents } from './ActivityDrawer'
import { Sidebar, useSidebarCollapsed } from './Sidebar'
import { Topbar } from './Topbar'

const TITLES: Record<string, string> = {
  '/': 'Overview',
  '/keywords': 'Keywords',
  '/issues': 'Issues',
  '/changes': 'Changes',
  '/migration': 'Migration',
  '/settings': 'Settings',
}

export function Shell() {
  const { site } = useSite()
  const { pathname } = useLocation()
  const outlet = useOutlet()
  const { data: overview } = useOverview(site.id)
  const { events, unseen, clearUnseen } = useLiveEvents(site.id)
  const [drawer, setDrawer] = useState(false)
  const [collapsed, setCollapsed] = useSidebarCollapsed()
  const title = TITLES[pathname] ?? TITLES[`/${pathname.split('/')[1]}`] ?? 'SEO Engine'

  return (
    <div className="flex h-full">
      <Sidebar pending={overview?.pending_change_sets} collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          title={title}
          liveCount={unseen}
          onOpenActivity={() => {
            setDrawer(true)
            clearUnseen()
          }}
        />
        <main className="scroll-thin flex-1 overflow-y-auto px-4 py-4">
          {/* useOutlet() freezes the outgoing route's element so the exit animation shows the old page, not the new one */}
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}>
              {outlet}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <ActivityDrawer open={drawer} onClose={() => setDrawer(false)} events={events} />
    </div>
  )
}

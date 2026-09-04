import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, ArrowRightLeft, FileText, Home, PanelLeftClose, PanelLeftOpen, Search, Settings } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router'
import { cn } from '@/lib/cn'

const NAV = [
  { to: '/', label: 'Overview', icon: Home, end: true },
  { to: '/keywords', label: 'Keywords', icon: Search },
  { to: '/issues', label: 'Issues', icon: AlertTriangle },
  { to: '/changes', label: 'Changes', icon: FileText },
  { to: '/migration', label: 'Migration', icon: ArrowRightLeft },
]

const KEY = 'seo-engine.sidebar'
const WIDE = 208
const NARROW = 76
const spring = { type: 'spring', stiffness: 420, damping: 38 } as const

/** Persisted collapse state; also toggles with the `[` key. */
export function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(KEY) === '1'
    } catch {
      return false
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(KEY, collapsed ? '1' : '0')
    } catch {
      /* private mode */
    }
  }, [collapsed])
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (e.key === '[' && tag !== 'INPUT' && tag !== 'TEXTAREA') setCollapsed((v) => !v)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])
  return [collapsed, setCollapsed] as const
}

function Item({ to, label, icon: Icon, end, badge, collapsed }: { to: string; label: string; icon: typeof Home; end?: boolean; badge?: number; collapsed: boolean }) {
  const { pathname } = useLocation()
  const active = end ? pathname === to : pathname.startsWith(to)
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      className={cn('group relative flex items-center gap-4 rounded-r-xl py-4 text-[0.95rem] transition-colors', collapsed ? 'justify-center px-0' : 'px-8', active ? 'text-ink' : 'text-ink-2 hover:text-ink')}
    >
      {active && <motion.span layoutId="nav-active" className="absolute inset-y-0 left-0 right-2 rounded-r-xl bg-brand-tint" transition={spring} />}
      {active && <motion.span layoutId="nav-bar" className="absolute inset-y-0 left-0 w-1 rounded-r bg-brand" transition={spring} />}
      <span className="relative">
        <Icon className={cn('size-5 transition-transform duration-300 group-hover:scale-110', active ? 'text-ink' : 'text-ink-2')} strokeWidth={1.8} />
        {collapsed && badge ? <span className="absolute -top-2 -right-2.5 grid min-w-[16px] place-items-center rounded-full bg-brand px-1 text-[10px] font-bold tabular-nums">{badge}</span> : null}
      </span>
      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.span
            key="label"
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -6 }}
            transition={{ duration: 0.16 }}
            className="relative flex flex-1 items-center whitespace-nowrap"
          >
            {label}
            {badge ? <span className="ml-auto rounded-full bg-brand px-2 py-0.5 text-xs font-semibold tabular-nums">{badge}</span> : null}
          </motion.span>
        )}
      </AnimatePresence>
    </NavLink>
  )
}

export function Sidebar({ pending, collapsed, onToggle }: { pending?: number; collapsed: boolean; onToggle: () => void }) {
  return (
    <motion.aside
      animate={{ width: collapsed ? NARROW : WIDE }}
      transition={spring}
      className="flex h-full shrink-0 flex-col overflow-hidden border-r border-line bg-surface"
    >
      <div className={cn('flex items-center pt-7 pb-6', collapsed ? 'justify-center' : 'justify-between pr-4 pl-8')}>
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div key="brand" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -6 }} transition={{ duration: 0.16 }} className="whitespace-nowrap text-[1.35rem] font-bold tracking-tight">
              SEO Engine
            </motion.div>
          )}
        </AnimatePresence>
        <button onClick={onToggle} className="btn btn-ghost btn-icon text-ink-3 hover:text-ink" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={`${collapsed ? 'Expand' : 'Collapse'} sidebar  [`}>
          {collapsed ? <PanelLeftOpen className="size-5" strokeWidth={1.8} /> : <PanelLeftClose className="size-5" strokeWidth={1.8} />}
        </button>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV.map((n) => (
          <Item key={n.to} {...n} collapsed={collapsed} badge={n.to === '/changes' ? pending : undefined} />
        ))}
      </nav>
      <div className="mt-auto pb-6">
        <Item to="/settings" label="Settings" icon={Settings} collapsed={collapsed} />
      </div>
    </motion.aside>
  )
}

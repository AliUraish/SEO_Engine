import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSites } from '@/api/hooks'
import type { Site } from '@/api/types'

interface SiteCtx {
  site: Site
  sites: Site[]
  select: (id: string) => void
}

const Ctx = createContext<SiteCtx | null>(null)
const KEY = 'seo-engine.site'

/** Resolves the current site; renders `fallback` while loading / when there are no sites yet. */
export function SiteProvider({ children, fallback, onboarding }: { children: ReactNode; fallback: ReactNode; onboarding: ReactNode }) {
  const { data: sites, isLoading } = useSites()
  const [selected, setSelected] = useState<string | null>(() => localStorage.getItem(KEY))
  useEffect(() => {
    if (selected) localStorage.setItem(KEY, selected)
  }, [selected])

  const site = useMemo(() => sites?.find((s) => s.id === selected) ?? sites?.[0] ?? null, [sites, selected])
  const value = useMemo(() => (site && sites ? { site, sites, select: setSelected } : null), [site, sites])

  if (isLoading) return <>{fallback}</>
  if (!value) return <>{onboarding}</>
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useSite(): SiteCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useSite outside SiteProvider')
  return ctx
}

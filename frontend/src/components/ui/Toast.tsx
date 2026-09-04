import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

type Tone = 'success' | 'error' | 'info'
interface Toast {
  id: number
  tone: Tone
  title: string
  detail?: string
}

const Ctx = createContext<{ push: (t: Omit<Toast, 'id'>) => void } | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random()
    setItems((xs) => [...xs, { ...t, id }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), t.tone === 'error' ? 6000 : 3500)
  }, [])
  const value = useMemo(() => ({ push }), [push])
  const icons = { success: <CheckCircle2 className="size-5 text-good" />, error: <AlertTriangle className="size-5 text-bad" />, info: <Info className="size-5 text-info" /> }
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-5 bottom-5 z-50 flex w-[360px] max-w-[calc(100vw-2.5rem)] flex-col gap-2">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.96 }}
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              className="card pointer-events-auto flex items-start gap-3 p-4 shadow-lift"
            >
              {icons[t.tone]}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">{t.title}</p>
                {t.detail && <p className="mt-0.5 text-xs text-ink-3 break-words">{t.detail}</p>}
              </div>
              <button className="text-ink-3 hover:text-ink" onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))} aria-label="Dismiss">
                <X className="size-4" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  )
}

export function useToast() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useToast outside ToastProvider')
  return ctx.push
}

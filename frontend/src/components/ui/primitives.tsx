import { animate, motion, useInView, useMotionValue, useTransform } from 'framer-motion'
import { ChevronRight } from 'lucide-react'
import { useEffect, useRef, type HTMLAttributes, type ReactNode } from 'react'
import { Link } from 'react-router'
import type { Severity } from '@/api/types'
import { cn } from '@/lib/cn'
import { SEVERITY_LABEL } from '@/lib/format'

// ---------- motion presets ----------
export const easeOut = [0.16, 1, 0.3, 1] as const

export const fadeUp = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: easeOut } },
}
export const stagger = (delay = 0.06) => ({ hidden: {}, show: { transition: { staggerChildren: delay } } })

/** Page wrapper: fades/slides in and staggers direct `motion` children. */
export function PageMotion({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div variants={stagger()} initial="hidden" animate="show" className={className}>
      {children}
    </motion.div>
  )
}

// ---------- card ----------
export function Card({ className, hover, children, ...rest }: HTMLAttributes<HTMLDivElement> & { hover?: boolean }) {
  return (
    <motion.div variants={fadeUp} className={cn('card', hover && 'card-hover', className)} {...(rest as object)}>
      {children}
    </motion.div>
  )
}

export function CardHeader({ title, action, className }: { title: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-center justify-between px-6 pt-6 pb-4', className)}>
      <h2 className="text-[1.25rem] font-semibold tracking-tight">{title}</h2>
      {action}
    </div>
  )
}

export function ViewAll({ to, label = 'View all' }: { to: string; label?: string }) {
  return (
    <Link to={to} className="link-arrow text-[0.925rem]">
      {label}
      <ChevronRight className="size-4" />
    </Link>
  )
}

// ---------- severity ----------
const sevTone: Record<Severity, string> = {
  critical: 'text-bad',
  high: 'text-bad',
  medium: 'text-warn',
  low: 'text-good',
  info: 'text-info',
}

export function SeverityDot({ severity, label = true, className }: { severity: Severity; label?: boolean; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 font-medium', sevTone[severity], className)}>
      <span className="size-2 rounded-full bg-current" />
      {label && SEVERITY_LABEL[severity]}
    </span>
  )
}

// ---------- chips ----------
export function Chip({ tone = 'neutral', children, className }: { tone?: 'neutral' | 'brand' | 'good' | 'warn' | 'bad' | 'info'; children: ReactNode; className?: string }) {
  const tones = {
    neutral: 'bg-line-2 text-ink-2',
    brand: 'bg-brand-tint text-ink',
    good: 'bg-good-tint text-good',
    warn: 'bg-warn-tint text-warn',
    bad: 'bg-bad-tint text-bad',
    info: 'bg-info-tint text-info',
  }
  return <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold', tones[tone], className)}>{children}</span>
}

// ---------- count up ----------
export function CountUp({ value, className, duration = 1.1 }: { value: number; className?: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const mv = useMotionValue(0)
  const rounded = useTransform(mv, (v) => Math.round(v).toString())
  useEffect(() => {
    if (!inView) return
    const controls = animate(mv, value, { duration, ease: easeOut })
    return controls.stop
  }, [inView, value, mv, duration])
  return (
    <motion.span ref={ref} className={className}>
      {rounded}
    </motion.span>
  )
}

// ---------- skeleton / empty ----------
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton', className)} />
}

export function Empty({ icon, title, hint, action }: { icon?: ReactNode; title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      {icon && <div className="mb-1 grid size-12 place-items-center rounded-full bg-brand-tint text-ink">{icon}</div>}
      <p className="font-semibold">{title}</p>
      {hint && <p className="max-w-sm text-sm text-ink-3">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function Divider({ className }: { className?: string }) {
  return <div className={cn('h-px w-full bg-line', className)} />
}

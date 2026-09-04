import type { Severity } from '@/api/types'

export const nf = new Intl.NumberFormat('en-US')
export const fmt = (n: number | null | undefined) => (n == null ? '—' : nf.format(n))

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 45) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  if (diff < 86400 * 14) return `${Math.round(diff / 86400)}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export const shortDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

export const SEVERITY_LABEL: Record<Severity, string> = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low', info: 'Info' }
export const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info']

export function healthLabel(score: number | null): { label: string; tone: 'good' | 'warn' | 'bad' | 'muted' } {
  if (score == null) return { label: 'No data', tone: 'muted' }
  if (score >= 80) return { label: 'Good', tone: 'good' }
  if (score >= 60) return { label: 'Needs work', tone: 'warn' }
  return { label: 'Poor', tone: 'bad' }
}

export const humanize = (s: string) => s.replace(/[_.-]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export const STATUS_LABEL: Record<string, string> = {
  pending_approval: 'Needs approval',
  approved: 'Approved',
  rejected: 'Rejected',
  awaiting_manual: 'Apply by hand',
  branch_ready: 'Branch ready',
  pr_opened: 'PR open',
  merged: 'Merged',
  verified: 'Verified live',
  failed: 'Not verified',
  rolled_back: 'Rolled back',
}

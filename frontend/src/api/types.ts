export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'

export interface Site {
  id: string
  name: string
  url: string
  repo: string | null
  default_branch: string
  gsc_property: string | null
  settings: Record<string, unknown> & {
    focus_keywords?: Record<string, string>
    exclude_paths?: string[]
    rank_drop_threshold?: number
    schedule?: { enabled?: boolean; crawl_interval_hours?: number; rank_sync_interval_hours?: number }
  }
  created_at: string
}

export interface Crawl {
  id: string
  site_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  started_at: string | null
  finished_at: string | null
  pages_found: number
  stats: Record<string, unknown> & { site_score?: number; by_severity?: Record<string, number> }
  error: string | null
  created_at: string
}

export interface Overview {
  site: Site
  site_score: number | null
  pages: number
  last_crawl: Crawl | null
  issues_by_severity: Partial<Record<Severity, number>>
  open_issues: number
  pending_change_sets: number
  tracked_keywords: number
  clicks_28d: number
  impressions_28d: number
  recent_drops: { at: string; message: string; keyword?: string; page?: string; from?: number; to?: number; delta?: number; suspect_change_sets?: string[] }[]
  integrations: { network: boolean; llm: boolean; gsc: boolean; github: boolean; repo: boolean }
}

export interface Page {
  id: string
  url: string
  path: string
  status_code: number | null
  title: string | null
  meta_description: string | null
  canonical: string | null
  h1: string[]
  word_count: number
  score: number | null
  fetched_at: string | null
  open_issues: number
}

export interface Issue {
  id: string
  page_id: string | null
  page_path: string | null
  rule_code: string
  severity: Severity
  message: string
  fix_hint: string | null
  details: Record<string, unknown>
  status: 'open' | 'fixing' | 'fixed' | 'ignored' | 'regressed'
  detected_at: string
  resolved_at: string | null
}

export interface PageDetail extends Page {
  snapshot: Record<string, unknown> | null
  issues: Issue[]
}

export interface Rule {
  code: string
  title: string
  category: string
  severity: Severity
}

export interface Keyword {
  id: string
  term: string
  source: 'gsc' | 'suggested' | 'manual'
  intent: string
  target_page_id: string | null
  target_path: string | null
  tracked: boolean
  opportunity: number
  bucket: 'striking_distance' | 'defend' | 'long_tail' | 'weak' | null
  notes: string | null
  clicks_28d: number
  impressions_28d: number
  position_28d: number | null
}

export interface RankingPoint {
  day: string
  page_url: string
  position: number
  clicks: number
  impressions: number
  ctr: number
}

export interface TrendPoint {
  day: string
  clicks: number
  impressions: number
  position: number | null
}

export interface ScorePoint {
  crawl_id: string
  at: string
  site_score: number
  pages: number
}

export type ChangeSetStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'awaiting_manual'
  | 'branch_ready'
  | 'pr_opened'
  | 'merged'
  | 'verified'
  | 'failed'
  | 'rolled_back'

export interface Change {
  id: string
  page_id: string | null
  page_path: string | null
  issue_id: string | null
  kind: string
  before: string | null
  after: string
  rationale: string
  generated_by: 'heuristic' | 'llm' | 'user'
  file_path: string | null
  apply_status: 'pending' | 'applied' | 'needs_manual' | 'verified' | 'failed'
  apply_note: string | null
}

export interface ChangeSet {
  id: string
  site_id: string
  title: string
  summary: string
  status: ChangeSetStatus
  created_by_agent: string
  expected_impact: number
  branch: string | null
  pr_number: number | null
  pr_url: string | null
  merge_sha: string | null
  decided_at: string | null
  decision_note: string | null
  created_at: string
  change_count: number
}

export interface ChangeSetDetail extends ChangeSet {
  changes: Change[]
}

export interface MigrationStep {
  phase: 'prepare' | 'stage' | 'validate' | 'cutover' | 'monitor'
  order: number
  title: string
  detail: string
  done: boolean
}

export interface MigrationPlanData {
  strategy: 'staged_subdomain' | 'direct_cutover'
  risk_score: number
  summary: string
  url_map: { old_path: string; new_path: string | null; confidence: number; method: string; clicks: number }[]
  redirects: { from: string; to: string; code: number }[]
  gaps: { path: string; kind: string; severity: Severity; detail: string }[]
  steps: MigrationStep[]
  stats: { old_pages: number; new_pages: number; mapped: number; unmapped: number; identical: number; old_traffic_covered: number | null; host_changes: boolean }
  narrative?: { executive_summary: string; top_risks: string[]; go_no_go: string }
}

export interface MigrationPlan {
  id: string
  site_id: string
  old_url: string
  new_url: string
  status: 'queued' | 'crawling' | 'ready' | 'failed'
  plan: MigrationPlanData | null
  error: string | null
  created_at: string
}

export interface Job {
  id: string
  site_id: string | null
  type: string
  payload: Record<string, unknown>
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  attempts: number
  max_attempts: number
  run_at: string
  parent_job_id: string | null
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface AgentEvent {
  id: string
  site_id: string | null
  job_id: string | null
  agent: string
  level: 'info' | 'warn' | 'error' | 'handoff'
  message: string
  data: Record<string, unknown>
  created_at: string
}

export interface AgentInfo {
  name: string
  handles: string[]
}

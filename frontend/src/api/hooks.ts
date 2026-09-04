import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from './client'
import type {
  AgentEvent,
  AgentInfo,
  Change,
  ChangeSet,
  ChangeSetDetail,
  Crawl,
  Issue,
  Job,
  Keyword,
  MigrationPlan,
  Overview,
  Page,
  PageDetail,
  RankingPoint,
  Rule,
  ScorePoint,
  Site,
  TrendPoint,
} from './types'

const ACTIVE_JOB_POLL = 2500

// ---------- sites ----------
export const useSites = () => useQuery({ queryKey: ['sites'], queryFn: () => api.get<Site[]>('/sites') })

export function useCreateSite() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; url: string; repo?: string | null; gsc_property?: string | null }) => api.post<Site>('/sites', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sites'] }),
  })
}

export function useUpdateSite(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Pick<Site, 'name' | 'repo' | 'default_branch' | 'gsc_property' | 'settings'>>) => api.patch<Site>(`/sites/${siteId}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sites'] })
      qc.invalidateQueries({ queryKey: ['overview', siteId] })
    },
  })
}

export const useOverview = (siteId: string) =>
  useQuery({ queryKey: ['overview', siteId], queryFn: () => api.get<Overview>(`/sites/${siteId}/overview`), refetchInterval: 10_000 })

export const useCrawls = (siteId: string) =>
  useQuery({ queryKey: ['crawls', siteId], queryFn: () => api.get<Crawl[]>(`/sites/${siteId}/crawls`), refetchInterval: 5000 })

export function useRunCrawl(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ job_id: string }>(`/sites/${siteId}/crawl`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs', siteId] })
      qc.invalidateQueries({ queryKey: ['crawls', siteId] })
    },
  })
}

export function useRunRankSync(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ job_id: string }>(`/sites/${siteId}/rank-sync`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs', siteId] }),
  })
}

// ---------- pages / issues ----------
export const useRules = () => useQuery({ queryKey: ['rules'], queryFn: () => api.get<Rule[]>('/rules'), staleTime: Infinity })

export const usePages = (siteId: string, params: { sort?: string; order?: string; q?: string } = {}) =>
  useQuery({ queryKey: ['pages', siteId, params], queryFn: () => api.get<Page[]>(`/sites/${siteId}/pages${qs(params)}`) })

export const usePage = (pageId: string | null) =>
  useQuery({ queryKey: ['page', pageId], queryFn: () => api.get<PageDetail>(`/pages/${pageId}`), enabled: !!pageId })

export const useIssues = (siteId: string, params: { status?: string; severity?: string; rule_code?: string } = {}) =>
  useQuery({ queryKey: ['issues', siteId, params], queryFn: () => api.get<Issue[]>(`/sites/${siteId}/issues${qs(params)}`) })

export function useUpdateIssue(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'open' | 'ignored' }) => api.patch<Issue>(`/issues/${id}`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['issues', siteId] })
      qc.invalidateQueries({ queryKey: ['overview', siteId] })
    },
  })
}

// ---------- keywords / analytics ----------
export const useKeywords = (siteId: string, params: { sort?: string; bucket?: string; tracked?: boolean; source?: string; q?: string } = {}) =>
  useQuery({ queryKey: ['keywords', siteId, params], queryFn: () => api.get<Keyword[]>(`/sites/${siteId}/keywords${qs(params)}`) })

export const useKeywordHistory = (keywordId: string | null) =>
  useQuery({ queryKey: ['keyword-history', keywordId], queryFn: () => api.get<RankingPoint[]>(`/keywords/${keywordId}/history`), enabled: !!keywordId })

export function useUpdateKeyword(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; tracked?: boolean; notes?: string }) => api.patch<Keyword>(`/keywords/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['keywords', siteId] }),
  })
}

export function useAddKeyword(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { term: string; tracked?: boolean }) => api.post<Keyword>(`/sites/${siteId}/keywords`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['keywords', siteId] }),
  })
}

export const useTrend = (siteId: string, days = 28) =>
  useQuery({ queryKey: ['trend', siteId, days], queryFn: () => api.get<TrendPoint[]>(`/sites/${siteId}/analytics/trend?days=${days}`) })

export const useScoreHistory = (siteId: string) =>
  useQuery({ queryKey: ['score-history', siteId], queryFn: () => api.get<ScorePoint[]>(`/sites/${siteId}/analytics/score-history`) })

// ---------- change sets ----------
export const useChangeSets = (siteId: string, status?: string) =>
  useQuery({ queryKey: ['change-sets', siteId, status], queryFn: () => api.get<ChangeSet[]>(`/sites/${siteId}/change-sets${qs({ status })}`), refetchInterval: 8000 })

export const useChangeSet = (id: string | null) =>
  useQuery({ queryKey: ['change-set', id], queryFn: () => api.get<ChangeSetDetail>(`/change-sets/${id}`), enabled: !!id, refetchInterval: 6000 })

export function useChangeSetAction(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action, note }: { id: string; action: 'approve' | 'reject' | 'mark-applied' | 'verify'; note?: string }) =>
      api.post<ChangeSetDetail>(`/change-sets/${id}/${action}`, { note }),
    onSuccess: (data) => {
      qc.setQueryData(['change-set', data.id], data)
      qc.invalidateQueries({ queryKey: ['change-sets', siteId] })
      qc.invalidateQueries({ queryKey: ['overview', siteId] })
      qc.invalidateQueries({ queryKey: ['jobs', siteId] })
    },
  })
}

export function useEditChange(changeSetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, after }: { id: string; after: string }) => api.patch<Change>(`/changes/${id}`, { after }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['change-set', changeSetId] }),
  })
}

export function useDropChange(changeSetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/changes/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['change-set', changeSetId] }),
  })
}

// ---------- migrations ----------
export const useMigrations = (siteId: string) =>
  useQuery({ queryKey: ['migrations', siteId], queryFn: () => api.get<MigrationPlan[]>(`/sites/${siteId}/migrations`), refetchInterval: 5000 })

export function useCreateMigration(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { old_url: string; new_url: string }) => api.post<MigrationPlan>(`/sites/${siteId}/migrations`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['migrations', siteId] }),
  })
}

export function useToggleStep(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, order, done }: { planId: string; order: number; done: boolean }) => api.patch<MigrationPlan>(`/migrations/${planId}/steps/${order}`, { done }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['migrations', siteId] }),
  })
}

// ---------- jobs / events ----------
export const useJobs = (siteId: string) =>
  useQuery({
    queryKey: ['jobs', siteId],
    queryFn: () => api.get<Job[]>(`/sites/${siteId}/jobs?limit=30`),
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === 'queued' || j.status === 'running') ? ACTIVE_JOB_POLL : 15_000),
  })

export const useEvents = (siteId: string, limit = 60) =>
  useQuery({ queryKey: ['events', siteId], queryFn: () => api.get<AgentEvent[]>(`/sites/${siteId}/events?limit=${limit}`) })

export const useAgents = () => useQuery({ queryKey: ['agents'], queryFn: () => api.get<AgentInfo[]>('/agents'), staleTime: Infinity })

export function useRetryJob(siteId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<Job>(`/jobs/${id}/retry`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs', siteId] }),
  })
}

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router'
import { Shell } from '@/components/layout/Shell'
import { ToastProvider } from '@/components/ui/Toast'
import { SiteProvider } from '@/lib/site'
import { ChangeSetDetail, Changes } from '@/pages/Changes'
import { Issues } from '@/pages/Issues'
import { Keywords } from '@/pages/Keywords'
import { Migration } from '@/pages/Migration'
import { Onboarding } from '@/pages/Onboarding'
import { Overview } from '@/pages/Overview'
import { Settings } from '@/pages/Settings'

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 5000, retry: 1, refetchOnWindowFocus: true } } })

function Splash() {
  return (
    <div className="grid h-full place-items-center">
      <div className="text-[1.45rem] font-bold tracking-tight opacity-40">SEO Engine</div>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <BrowserRouter>
          <SiteProvider fallback={<Splash />} onboarding={<Onboarding />}>
            <Routes>
              <Route element={<Shell />}>
                <Route index element={<Overview />} />
                <Route path="keywords" element={<Keywords />} />
                <Route path="issues" element={<Issues />} />
                <Route path="changes" element={<Changes />} />
                <Route path="changes/:id" element={<ChangeSetDetail />} />
                <Route path="migration" element={<Migration />} />
                <Route path="settings" element={<Settings />} />
              </Route>
            </Routes>
          </SiteProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}

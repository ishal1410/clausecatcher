/**
 * preview-main.tsx — scratch mount for screenshotting Report in isolation
 * with fake data. Not imported by the real app; entry point is
 * frontend/report-preview.html. `?state=` picks a variant:
 * (default) two contradictions | empty | risk | loading | error
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../../index.css'
import Report from './Report'
import type { Report as ReportData } from '../../lib/protocol'

const now = Date.now()
const fakeReport: ReportData = {
  contract_clauses_referenced: ['4.2', '5.1', '7.3'],
  contradictions: [
    {
      sentence: 'We can also do a verbal discount for a big client.',
      section_number: '4.2',
      literal_text: 'All discounts require written approval from a sales director.',
      t: new Date(now - 9 * 60_000).toISOString(),
    },
    {
      sentence: "Sure, we'll guarantee same-day support response any time.",
      section_number: '7.3',
      literal_text: 'Support response times are best-effort within standard business hours (9am-6pm ET).',
      t: new Date(now - 3 * 60_000).toISOString(),
    },
  ],
  transcript_count: 47,
  started_at: new Date(now - 12 * 60_000).toISOString(),
  ended_at: new Date(now).toISOString(),
  est_cost_usd: 0.0842,
  claim_check_calls: 47,
  claim_check_errors: 1,
}

const state = new URLSearchParams(location.search).get('state')
const report: ReportData | null =
  state === 'loading' || state === 'error'
    ? null
    : state === 'empty'
      ? { ...fakeReport, contradictions: [], claim_check_errors: 0 }
      : state === 'risk'
        ? { ...fakeReport, transcript_count: 6 }
        : fakeReport

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Report
      report={report}
      error={state === 'error' ? 'Report service returned 502 Bad Gateway.' : null}
      onRetry={() => console.log('[preview] onRetry fired')}
      onNewSession={() => console.log('[preview] onNewSession fired')}
    />
  </StrictMode>,
)

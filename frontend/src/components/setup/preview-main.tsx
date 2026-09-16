/**
 * preview-main.tsx — standalone mount for visual QA, per the build task:
 * mocks fetch so Setup.tsx can be screenshotted without a running backend
 * or any AssemblyAI/Gemini calls. Not part of the app bundle (App.tsx
 * loads Setup.tsx directly); only reachable via setup-preview.html.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../../index.css'
import Setup from './Setup'
import type { Clause } from '../../lib/protocol'

// Mirrors spikes/harness/fake_contract.json
const DEMO_CLAUSES: Clause[] = [
  {
    section_number: '3.1',
    title: 'Pricing & Seat Cap',
    literal_text: 'Flat $48,000 up to 50 seats; extra seats need signed written amendment; no automatic or verbal discounting.',
  },
  {
    section_number: '4.2',
    title: 'Renewal',
    literal_text: 'Auto-renews 12 months unless written notice 60 days before term ends; no mid-term termination.',
  },
  {
    section_number: '5.3',
    title: 'Data Retention',
    literal_text: '30-day recoverable archive then permanent deletion.',
  },
  {
    section_number: '6.1',
    title: 'Support SLA',
    literal_text: 'P1 within 4 business hours Mon-Fri 9-6 ET; 24/7 requires Premium Support Addendum.',
  },
]

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

const realFetch = window.fetch.bind(window)
window.fetch = async (input, init) => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  const method = init?.method ?? 'GET'

  if (url.endsWith('/api/contract/demo') && method === 'POST') {
    await new Promise((resolve) => setTimeout(resolve, 800))
    return jsonResponse({ clauses: DEMO_CLAUSES })
  }
  if (url.endsWith('/api/contract') && method === 'POST') {
    await new Promise((resolve) => setTimeout(resolve, 800))
    return jsonResponse({ clauses: DEMO_CLAUSES })
  }
  if (url.endsWith('/api/consent') && method === 'POST') {
    return jsonResponse({ consent: true })
  }
  if (url.endsWith('/api/session/start') && method === 'POST') {
    return jsonResponse({ session_id: 'preview-session' })
  }
  return realFetch(input, init)
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <div className="min-h-dvh bg-bg-base">
      <Setup onReady={(sessionId, clauses) => console.log('[preview] onReady', sessionId, clauses.length)} />
    </div>
  </StrictMode>,
)

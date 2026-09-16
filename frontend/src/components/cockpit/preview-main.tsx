/**
 * preview-main.tsx — standalone mount for visually verifying Cockpit.tsx
 * without a live backend. Scripts a fake session through the exact
 * UI_SCREENS_SPEC.md §4a beat sheet: clean transcript lines land, then one
 * trips a contradiction alert on §3.1, the voice agent "speaks" (sine
 * agentLevel) for ~5s, then "Spoken verbatim" confirms. Not imported by
 * the real app; entry point is cockpit-preview.html.
 */
import { StrictMode, useCallback, useEffect, useReducer, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import '../../index.css'
import Cockpit from './Cockpit'
import type { AlertRecord, TranscriptLine } from '../../hooks/useSession'
import type { Clause, Report } from '../../lib/protocol'

// Same clauses as the server's demo contract (spikes/harness/fake_contract.json).
const CLAUSES: Clause[] = [
  { section_number: '3.1', title: 'Pricing & Seat Cap', literal_text: 'Flat $48,000 up to 50 seats; extra seats need signed written amendment; no automatic or verbal discounting.' },
  { section_number: '4.2', title: 'Renewal', literal_text: 'Auto-renews 12 months unless written notice 60 days before term ends; no mid-term termination.' },
  { section_number: '5.3', title: 'Data Retention', literal_text: '30-day recoverable archive then permanent deletion.' },
  { section_number: '6.1', title: 'Support SLA', literal_text: 'P1 within 4 business hours Mon-Fri 9-6 ET; 24/7 requires Premium Support Addendum.' },
]

interface FakeState {
  connected: boolean
  status: { stt: string; voice: string } | null
  transcript: TranscriptLine[]
  alerts: AlertRecord[]
  clauses: Clause[]
  agentSpeaking: boolean
  report: Report | null
  error: string | null
}

const initial: FakeState = {
  connected: false,
  status: null,
  transcript: [],
  alerts: [],
  clauses: [],
  agentSpeaking: false,
  report: null,
  error: null,
}

type Action = Partial<FakeState> | { pushTranscript: TranscriptLine } | { replaceLastTranscript: TranscriptLine } | { pushAlert: AlertRecord }

function reducer(state: FakeState, action: Action): FakeState {
  if ('pushTranscript' in action) return { ...state, transcript: [...state.transcript, action.pushTranscript] }
  if ('replaceLastTranscript' in action)
    return { ...state, transcript: [...state.transcript.slice(0, -1), action.replaceLastTranscript] }
  if ('pushAlert' in action) return { ...state, alerts: [action.pushAlert, ...state.alerts] }
  return { ...state, ...action }
}

function useFakeSession() {
  const [state, dispatch] = useReducer(reducer, initial)
  const agentLevelRef = useRef(0)
  const micLevelRef = useRef(0)

  useEffect(() => {
    const timers: number[] = []
    const t = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, ms))

    // Demo-cut pacing (UI_SCREENS_SPEC §4a): clean lines, then the
    // contradiction at ~8s, voice reads the clause ~8.5-13.5s, then verbatim.
    const say = (at: number, partial: string, final: string) => {
      t(at, () => dispatch({ pushTranscript: { text: partial, final: false } }))
      t(at + 600, () => dispatch({ replaceLastTranscript: { text: final, final: true } }))
    }
    t(200, () => dispatch({ connected: true, status: { stt: 'connected', voice: 'connected' } }))
    say(600, 'Thanks for making time today, I', 'Thanks for making time today, I know renewal is coming up.')
    say(2200, 'Your fifty seats stay locked', 'Your fifty seats stay locked at the flat $48,000 rate.')
    say(4000, 'Support is P1 within four', 'Support is P1 within four business hours, Monday to Friday.')
    say(7000, 'If you sign this week, we can', 'If you sign this week, we can do a verbal discount on the extra seats.')
    t(8100, () =>
      dispatch({
        pushAlert: {
          section_number: '3.1',
          title: 'Pricing & Seat Cap',
          literal_text: CLAUSES[0].literal_text,
          sentence: 'If you sign this week, we can do a verbal discount on the extra seats.',
          t: new Date().toISOString(),
        },
      }),
    )
    t(8500, () => dispatch({ agentSpeaking: true }))
    t(13500, () => dispatch({ agentSpeaking: false }))
    say(15000, 'Understood, I will get', 'Understood, I will get that approved in writing first.')

    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [])

  // Sine-driven amplitude for the speaking window, written to a ref then
  // pushed into state at ~20Hz so VoiceOrb's `level` prop moves smoothly
  // without a raw scroll/rAF-into-state antipattern for anything but this
  // harness-only level number.
  const [, forceTick] = useReducer((n: number) => n + 1, 0)
  useEffect(() => {
    let raf: number
    const start = performance.now()
    function loop(now: number) {
      const elapsed = (now - start) / 1000
      agentLevelRef.current = state.agentSpeaking ? 0.2 + 0.45 * Math.abs(Math.sin(elapsed * 7) * Math.sin(elapsed * 2.3)) : 0
      micLevelRef.current = state.connected && !state.agentSpeaking ? 0.08 + 0.05 * Math.abs(Math.sin(elapsed * 2.3)) : 0
      forceTick()
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [state.agentSpeaking, state.connected])

  // stable like the real hook's useCallback'd senders, so memo() is exercised honestly
  const sendSimulate = useCallback((text: string) => dispatch({ pushTranscript: { text, final: true } }), [])
  const sendAsk = useCallback(() => {}, [])

  return {
    state,
    micLevel: micLevelRef.current,
    agentLevel: agentLevelRef.current,
    start: () => {},
    stop: () => {},
    sendSimulate,
    sendAsk,
  }
}

const noop = () => {}

function Preview() {
  const session = useFakeSession()
  return (
    <div style={{ height: '100vh', width: '100vw' }}>
      <Cockpit session={session} clauses={CLAUSES} onEnd={noop} />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Preview />
  </StrictMode>,
)

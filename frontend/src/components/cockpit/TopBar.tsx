import { memo, useEffect, useRef, useState } from 'react'
import { ChevronRight, PhoneOff, ShieldCheck } from 'lucide-react'
import { StatusPill, claimPillState, type PillState } from './StatusPill'

function toPillState(raw: string | undefined, connected: boolean, active: boolean): PillState {
  if (!connected || !raw) return 'connecting'
  if (raw === 'error') return 'error'
  if (raw !== 'connected') return 'disabled'
  return active ? 'active' : 'connected'
}

function formatElapsed(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/** Owns its own 1s timer so the tick never re-renders the rest of the cockpit. */
function ElapsedTimer({ connected }: { connected: boolean }) {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    // a dead session freezes the clock at its last value; it must never keep
    // ticking as if the call were live (DEMO_DAY_BUGS.md finding 2)
    if (!connected) return
    startRef.current ??= Date.now()
    const id = window.setInterval(() => {
      if (startRef.current !== null) setElapsed(Math.floor((Date.now() - startRef.current) / 1000))
    }, 1000)
    return () => window.clearInterval(id)
  }, [connected])

  return <span className="font-mono text-[13px] tabular-nums text-text-secondary">{formatElapsed(elapsed)}</span>
}

const Arrow = <ChevronRight size={14} strokeWidth={1.75} className="shrink-0 text-border-strong" aria-hidden />

/** Top bar. The three pills are laid out as the actual pipeline
 * (STT -> claim check -> voice) and light up when that stage is working. */
export const TopBar = memo(function TopBar({
  connected,
  stt,
  voice,
  claimCheck,
  sttStreaming,
  geminiActive,
  voiceSpeaking,
  ended,
  onEnd,
}: {
  connected: boolean
  stt: string | undefined
  voice: string | undefined
  /** `status.claim_check` off the wire. Optional: Cockpit.tsx is owned by another agent. */
  claimCheck?: string
  sttStreaming: boolean
  geminiActive: boolean
  voiceSpeaking: boolean
  /** set once the session is over, so the bar can say so instead of "Offline" */
  ended?: string | null
  onEnd: () => void
}) {
  return (
    <header
      className="cc-glass relative z-10 flex h-16 shrink-0 items-center justify-between gap-4 px-5"
      style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}
    >
      <div className="flex items-center gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand/15 text-brand-light">
          <ShieldCheck size={18} strokeWidth={1.75} />
        </span>
        <span className="font-display text-[16px] font-bold tracking-tight text-text-primary">ClauseCatcher</span>
        <span className="ml-1 inline-flex items-center gap-2 rounded-md border border-border bg-bg-sunken/60 px-2 py-1">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-primary">
            <span
              className={connected ? 'h-1.5 w-1.5 rounded-full bg-risk-high cc-anim-livepulse' : 'h-1.5 w-1.5 rounded-full bg-border-strong'}
              aria-hidden
            />
            {connected ? 'Live' : ended ? 'Ended' : 'Offline'}
          </span>
          <span className="h-3 w-px bg-border" aria-hidden />
          <ElapsedTimer connected={connected} />
        </span>
      </div>

      <div className="hidden items-center gap-1.5 md:flex" aria-label="Processing pipeline">
        <StatusPill label="AssemblyAI STT" state={toPillState(stt, connected, sttStreaming)} />
        {Arrow}
        <StatusPill label="Gemini check" state={claimPillState(claimCheck, connected, geminiActive)} />
        {Arrow}
        <StatusPill label="AssemblyAI Voice" state={toPillState(voice, connected, voiceSpeaking)} />
      </div>

      <button
        onClick={onEnd}
        className="inline-flex h-10 items-center gap-2 rounded-full border border-risk-high/50 bg-risk-high/10 px-4 text-[13px] font-semibold text-risk-high-text transition-[background-color,transform] duration-150 hover:bg-risk-high/20 active:scale-[0.98]"
      >
        <PhoneOff size={15} strokeWidth={1.75} />
        End call
      </button>
    </header>
  )
})

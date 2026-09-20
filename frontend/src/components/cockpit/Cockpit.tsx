/**
 * Cockpit.tsx — the live call cockpit, UI_SCREENS_SPEC.md §4. Top bar
 * (pipeline pills) over three panes: transcript | verdict + alert evidence +
 * clause watchlist | voice orb + controls. This is the demo video's money
 * shot, so the alert beat (§4a) is choreographed here: phrase underline
 * sweep -> red frame flash + card flare -> supporting UI recedes ("alert
 * live") -> the literal clause is marked "reading aloud" while the voice
 * speaks -> "Spoken verbatim".
 *
 * Performance: useSession's micLevel/agentLevel change at audio-chunk rate.
 * The shell below only puts the level into LevelContext; everything else is
 * the memo'd CockpitBody, whose props are stable between ticks. So a level
 * tick re-renders this shell + the one context consumer (VoiceOrb), not the
 * panes.
 *
 * Glass lives only on chrome (top bar, right rail); evidence stays opaque.
 */
import { memo, useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { MicOff } from 'lucide-react'
import './cockpit.css'
import { TopBar } from './TopBar'
import { TranscriptPane } from './TranscriptPane'
import { AlertStack, alertKey } from './AlertStack'
import { CallVerdict } from './CallVerdict'
import { LevelContext, VoiceOrb } from './VoiceOrb'
import { ClauseRiskMeter } from './ClauseRiskMeter'
import { CommandBar } from './CommandBar'
import type { useSession } from '../../hooks/useSession'
import type { Clause } from '../../lib/protocol'

type Session = ReturnType<typeof useSession>

const NO_KEYS: ReadonlySet<string> = new Set()
const ALERT_FOCUS_MS = 4000

/** A failed getUserMedia is a permanent condition for this call, not a
 * 5-second toast: once it fires, the cockpit says so until a new session
 * starts (which remounts this component). Detected from the error text
 * because useSession has no mic flag of its own. */
const isMicError = (error: string | null) => !!error && /microphone|getusermedia|audio input/i.test(error)

export default function Cockpit({ session, clauses, onEnd }: { session: Session; clauses: Clause[]; onEnd: () => void }) {
  const { state, micLevel, agentLevel, sendSimulate, sendAsk } = session
  return (
    <LevelContext value={state.agentSpeaking ? agentLevel : micLevel}>
      <CockpitBody state={state} clauses={clauses} onEnd={onEnd} sendAsk={sendAsk} sendSimulate={sendSimulate} />
    </LevelContext>
  )
}

const CockpitBody = memo(function CockpitBody({
  state,
  clauses,
  onEnd,
  sendAsk,
  sendSimulate,
}: {
  state: Session['state']
  clauses: Clause[]
  onEnd: () => void
  sendAsk: Session['sendAsk']
  sendSimulate: Session['sendSimulate']
}) {
  const reducedMotion = useReducedMotion()
  const { alerts, agentSpeaking, transcript, connected } = state
  const newestKey = alerts[0] ? alertKey(alerts[0]) : null

  // "Spoken verbatim": the protocol has no per-alert verbatim-result message,
  // so derive it from the newest alert's agent_speaking start->stop edge.
  // Tracked with the adjust-state-during-render pattern (no effect, no
  // mutable Set, so memo'd children see a new reference when it changes).
  // ponytail: heuristic — an `ask` answer spoken right after an unspoken
  // alert would also confirm it; upgrade when the server sends a real flag.
  const [confirmedKeys, setConfirmedKeys] = useState(NO_KEYS)
  const [prevSpeaking, setPrevSpeaking] = useState(agentSpeaking)
  if (prevSpeaking !== agentSpeaking) {
    setPrevSpeaking(agentSpeaking)
    if (prevSpeaking && newestKey && !confirmedKeys.has(newestKey)) setConfirmedKeys(new Set(confirmedKeys).add(newestKey))
  }

  // Alert focus window: from arrival until spoken (or 4s if the voice never starts).
  const [recentKey, setRecentKey] = useState<string | null>(null)
  useEffect(() => {
    if (!newestKey) return
    setRecentKey(newestKey)
    const id = window.setTimeout(() => setRecentKey(null), ALERT_FOCUS_MS)
    return () => window.clearTimeout(id)
  }, [newestKey])
  const alertLive = !!newestKey && !confirmedKeys.has(newestKey) && (agentSpeaking || recentKey === newestKey)

  // Gemini sends no status message; light its pill briefly when a finalized
  // line or alert arrives (when the claim check actually runs). ponytail: display-only.
  const finalCount = transcript.reduce((n, l) => n + (l.final ? 1 : 0), 0)
  const [geminiActive, setGeminiActive] = useState(false)
  useEffect(() => {
    if (finalCount === 0) return
    setGeminiActive(true)
    const id = window.setTimeout(() => setGeminiActive(false), 900)
    return () => window.clearTimeout(id)
  }, [finalCount, alerts.length])

  // Sticky mic state. state.error is transient (App toasts it for 5s); the
  // mic being blocked is not, so latch it and keep saying so.
  const [micBlocked, setMicBlocked] = useState(false)
  if (!micBlocked && isMicError(state.error)) setMicBlocked(true)

  const sttStreaming = transcript.length > 0 && !transcript[transcript.length - 1].final
  const listening = connected && !agentSpeaking && !micBlocked

  return (
    <div data-alert-live={alertLive} className="cc-cockpit relative flex w-full flex-col bg-bg-base text-text-primary">
      <TopBar
        connected={connected}
        stt={state.status?.stt}
        voice={state.status?.voice}
        sttStreaming={sttStreaming}
        geminiActive={geminiActive}
        voiceSpeaking={agentSpeaking}
        claimCheck={state.status?.claim_check}
        onEnd={onEnd}
      />

      {/* Three panes at lg; below that .cc-panes flips to a flex column
          (cockpit.css) and `order` puts the alert stack first, the controls
          next and the transcript last — so a judge on a phone can still run
          the demo and still reach "End call". */}
      <div className="cc-panes grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[280px_1fr_320px]">
        <div className="order-3 h-60 min-h-0 grow overflow-hidden border-t border-border/60 lg:order-none lg:h-auto lg:grow-0 lg:overflow-visible lg:border-t-0">
          <TranscriptPane transcript={transcript} alerts={alerts} />
        </div>

        <main aria-label="Call verdict and contradiction alerts" className="order-1 flex min-h-0 min-w-0 flex-col bg-bg-sunken lg:order-none">
          <div className="cc-verdict shrink-0">
            <CallVerdict
              connected={connected}
              checked={finalCount}
              contradictions={alerts.length}
              spoken={confirmedKeys.size}
              claimCheck={state.status?.claim_check}
              checkFailed={state.checkFailed}
            />
          </div>
          <AlertStack
            alerts={alerts}
            agentSpeaking={agentSpeaking}
            voiceReady={state.status?.voice === 'connected'}
            confirmedKeys={confirmedKeys}
            clauseCount={clauses.length}
          />
          <ClauseRiskMeter clauses={clauses} alerts={alerts} askedClauses={state.clauses} />
        </main>

        <aside
          aria-label="Voice agent and call controls"
          className="cc-glass order-2 flex min-h-0 min-w-0 flex-col gap-4 overflow-visible border-t border-text-primary/8 p-4 lg:order-none lg:overflow-y-auto lg:border-l lg:border-t-0"
        >
          {/* flex-1: the orb card owns the rail's spare height, so no dead band under
              the controls. Hidden on a phone, where that height belongs to the controls. */}
          <div className="hidden min-h-[220px] flex-1 items-center justify-center rounded-lg border border-text-primary/8 bg-bg-sunken/40 py-6 sm:flex">
            <VoiceOrb speaking={agentSpeaking} listening={listening} connected={connected} micBlocked={micBlocked} />
          </div>

          {micBlocked && (
            <p
              role="status"
              className="flex items-start gap-2.5 rounded-lg border border-risk-medium/40 bg-risk-medium/[0.08] p-3 text-[12px] leading-snug text-text-secondary"
            >
              <MicOff size={14} strokeWidth={1.75} className="mt-0.5 shrink-0 text-risk-medium-text" aria-hidden />
              <span>
                <strong className="font-semibold text-text-primary">Microphone blocked.</strong> This browser did not hand over the mic, so
                nothing is being transcribed. Type a line into Simulate rep line below to run the same check.
              </span>
            </p>
          )}

          <CommandBar
            clauses={clauses}
            answered={state.clauses}
            voiceReady={state.status?.voice === 'connected'}
            onAsk={sendAsk}
            onSimulate={sendSimulate}
          />
        </aside>
      </div>

      {/* Frame flash: one red inset pulse around the whole cockpit per new
          alert, so the beat reads even on a small 720p video frame. */}
      {newestKey && !reducedMotion && (
        <motion.div
          key={newestKey}
          className="pointer-events-none absolute inset-0 z-20"
          style={{
            boxShadow:
              'inset 0 0 0 2px color-mix(in oklab, var(--risk-high) 80%, transparent), inset 0 0 140px color-mix(in oklab, var(--risk-high) 30%, transparent)',
          }}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 1, 0.6, 0] }}
          transition={{ duration: 1.6, times: [0, 0.12, 0.4, 1], ease: 'easeOut' }}
          aria-hidden
        />
      )}
    </div>
  )
})

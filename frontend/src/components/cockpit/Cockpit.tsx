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
import './cockpit.css'
import { TopBar } from './TopBar'
import { TranscriptPane } from './TranscriptPane'
import { AlertStack, alertKey } from './AlertStack'
import { CallVerdict } from './CallVerdict'
import { LevelContext, VoiceOrb } from './VoiceOrb'
import { ClauseRiskMeter } from './ClauseRiskMeter'
import { CommandBar } from './CommandBar'
import { ErrorToast } from './ErrorToast'
import type { useSession } from '../../hooks/useSession'
import type { Clause } from '../../lib/protocol'

type Session = ReturnType<typeof useSession>

const NO_KEYS: ReadonlySet<string> = new Set()
const ALERT_FOCUS_MS = 4000

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

  const sttStreaming = transcript.length > 0 && !transcript[transcript.length - 1].final
  const listening = connected && !agentSpeaking

  return (
    <div data-alert-live={alertLive} className="cc-cockpit relative flex h-full min-h-[480px] w-full flex-col bg-bg-base text-text-primary">
      <TopBar
        connected={connected}
        stt={state.status?.stt}
        voice={state.status?.voice}
        sttStreaming={sttStreaming}
        geminiActive={geminiActive}
        voiceSpeaking={agentSpeaking}
        onEnd={onEnd}
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[280px_1fr_320px]">
        <div className="hidden min-h-0 lg:block">
          <TranscriptPane transcript={transcript} alerts={alerts} />
        </div>

        <main className="flex min-h-0 min-w-0 flex-col bg-bg-sunken">
          <CallVerdict connected={connected} checked={finalCount} contradictions={alerts.length} spoken={confirmedKeys.size} />
          <AlertStack
            alerts={alerts}
            agentSpeaking={agentSpeaking}
            voiceReady={state.status?.voice === 'connected'}
            confirmedKeys={confirmedKeys}
            clauseCount={clauses.length}
          />
          <ClauseRiskMeter clauses={clauses} alerts={alerts} askedClauses={state.clauses} />
        </main>

        <aside className="cc-glass hidden min-h-0 flex-col gap-4 overflow-y-auto border-l border-text-primary/8 p-4 lg:flex">
          {/* flex-1: the orb card owns the rail's spare height, so no dead band under the controls */}
          <div className="flex min-h-[220px] flex-1 items-center justify-center rounded-lg border border-text-primary/8 bg-bg-sunken/40 py-6">
            <VoiceOrb speaking={agentSpeaking} listening={listening} connected={connected} />
          </div>
          <CommandBar clauses={clauses} onAsk={sendAsk} onSimulate={sendSimulate} />
        </aside>

        {/* Mobile fallback: cockpit is a desktop operator surface (UI_SCREENS_SPEC.md §1). */}
        <div className="border-t border-border/60 bg-bg-sunken px-4 py-2 text-center text-[12px] text-text-muted lg:hidden">
          Best viewed on a larger screen during a live call.
        </div>
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

      <ErrorToast message={state.error} />
    </div>
  )
})

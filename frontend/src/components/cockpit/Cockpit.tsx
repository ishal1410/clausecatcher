/**
 * Cockpit.tsx — the live call cockpit, UI_SCREENS_SPEC.md §4. Top bar
 * (pipeline pills) over three panes: transcript | verdict + alert evidence +
 * clause watchlist | voice orb + controls. This is the demo video's money
 * shot, so the alert beat (§4a) is choreographed here: phrase underline
 * sweep -> red bloom + card flare -> supporting UI recedes ("alert live")
 * -> voice reads the clause -> "Spoken verbatim".
 *
 * Performance: useSession's micLevel/agentLevel update at audio-chunk rate
 * and re-render this component every time. Every pane below is memo()'d and
 * receives only stable references or primitives, so a level tick re-renders
 * Cockpit + VoiceOrb only (VoiceOrb then pushes the level into a CSS var).
 *
 * Glass lives only on chrome (top bar, right rail); evidence stays opaque.
 */
import { useEffect, useState } from 'react'
import './cockpit.css'
import { TopBar } from './TopBar'
import { TranscriptPane } from './TranscriptPane'
import { AlertStack, alertKey } from './AlertStack'
import { CallVerdict } from './CallVerdict'
import { VoiceOrb } from './VoiceOrb'
import { ClauseRiskMeter } from './ClauseRiskMeter'
import { CommandBar } from './CommandBar'
import { ErrorToast } from './ErrorToast'
import type { useSession } from '../../hooks/useSession'
import type { Clause } from '../../lib/protocol'

const NO_KEYS: ReadonlySet<string> = new Set()
const ALERT_FOCUS_MS = 4000

export default function Cockpit({
  session,
  clauses,
  onEnd,
}: {
  session: ReturnType<typeof useSession>
  clauses: Clause[]
  onEnd: () => void
}) {
  const { state, micLevel, agentLevel, sendSimulate, sendAsk } = session
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
    <div data-alert-live={alertLive} className="cc-cockpit flex h-full min-h-[480px] w-full flex-col bg-bg-base text-text-primary">
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
          <AlertStack alerts={alerts} agentSpeaking={agentSpeaking} voiceReady={state.status?.voice === 'connected'} confirmedKeys={confirmedKeys} />
          <ClauseRiskMeter clauses={clauses} alerts={alerts} askedClauses={state.clauses} />
        </main>

        <aside className="cc-glass hidden min-h-0 flex-col gap-4 overflow-y-auto border-l border-text-primary/8 p-4 lg:flex">
          <div className="flex justify-center rounded-lg border border-text-primary/8 bg-bg-sunken/40 py-6">
            <VoiceOrb level={agentSpeaking ? agentLevel : micLevel} speaking={agentSpeaking} listening={listening} connected={connected} />
          </div>
          <CommandBar clauses={clauses} onAsk={sendAsk} onSimulate={sendSimulate} />
        </aside>

        {/* Mobile fallback: cockpit is a desktop operator surface (UI_SCREENS_SPEC.md §1). */}
        <div className="border-t border-border/60 bg-bg-sunken px-4 py-2 text-center text-[12px] text-text-muted lg:hidden">
          Best viewed on a larger screen during a live call.
        </div>
      </div>

      <ErrorToast message={state.error} />
    </div>
  )
}

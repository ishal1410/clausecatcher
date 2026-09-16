import { memo } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ShieldCheck } from 'lucide-react'
import { AlertCard, type VoiceState } from './AlertCard'
import type { AlertRecord } from '../../hooks/useSession'

export const alertKey = (a: AlertRecord) => a.t + a.section_number

export const AlertStack = memo(function AlertStack({
  alerts,
  agentSpeaking,
  voiceReady,
  confirmedKeys,
  clauseCount,
}: {
  alerts: AlertRecord[]
  agentSpeaking: boolean
  voiceReady: boolean
  confirmedKeys: ReadonlySet<string>
  clauseCount: number
}) {
  const reducedMotion = useReducedMotion()
  const newest = alerts[0]

  function voiceFor(a: AlertRecord, i: number): VoiceState {
    if (confirmedKeys.has(alertKey(a))) return 'spoken'
    if (i !== 0) return 'none'
    if (agentSpeaking) return 'speaking'
    return voiceReady ? 'queued' : 'none'
  }

  return (
    <section className="relative flex min-h-0 flex-1 flex-col">
      {/* One-shot red bloom behind the stack on each new alert: the "flash"
          transient that makes the alert beat read on a 720p video frame. */}
      {newest && !reducedMotion && (
        <motion.div
          key={alertKey(newest)}
          className="pointer-events-none absolute inset-x-0 -top-24 h-[420px]"
          style={{ background: 'radial-gradient(60% 55% at 50% 30%, color-mix(in oklab, var(--risk-high) 32%, transparent), transparent 70%)' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 1, 0.25] }}
          transition={{ duration: 1.4, times: [0, 0.18, 1], ease: 'easeOut' }}
          aria-hidden
        />
      )}

      <div className="relative flex h-9 shrink-0 items-end justify-between px-5">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
          Contradiction alerts
          {alerts.length > 0 && <span className="ml-1.5 font-mono text-risk-high-text">{alerts.length}</span>}
        </h2>
        {alerts.length > 1 && <span className="text-[11px] text-text-muted">Newest first</span>}
      </div>

      <div className="relative min-h-0 flex-1 overflow-y-auto px-5 pb-4 pt-2" aria-live="polite">
        {alerts.length === 0 ? (
          <motion.div
            initial={reducedMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex h-full min-h-32 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-safe/25 bg-safe/[0.04] px-6 text-center"
          >
            {/* "armed" radar: two rings expanding off the shield, CSS-only */}
            <span className="relative flex h-14 w-14 items-center justify-center" aria-hidden>
              <span className="cc-anim-radar absolute inset-0 rounded-full border border-safe/40" />
              <span className="cc-anim-radar absolute inset-0 rounded-full border border-safe/40" style={{ animationDelay: '1.4s' }} />
              <span className="relative flex h-11 w-11 items-center justify-center rounded-full bg-safe/12 text-safe">
                <ShieldCheck size={22} strokeWidth={1.75} />
              </span>
            </span>
            <p className="font-display text-[17px] font-semibold text-text-primary">
              {clauseCount > 0 ? `Guarding ${clauseCount} signed clause${clauseCount === 1 ? '' : 's'}` : 'No contradictions yet'}
            </p>
            <p className="max-w-sm text-[13px] leading-relaxed text-text-muted">
              Every finalized sentence is checked against the contract. A contradiction lands here with the literal clause, read aloud.
            </p>
          </motion.div>
        ) : (
          <div className="space-y-3">
            <AnimatePresence mode="popLayout" initial={false}>
              {alerts.map((alert, i) => (
                <AlertCard key={alertKey(alert)} alert={alert} isNewest={i === 0} voice={voiceFor(alert, i)} />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </section>
  )
})

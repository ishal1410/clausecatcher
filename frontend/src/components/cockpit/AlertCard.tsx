import { memo, useRef, type MouseEvent } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { CheckCircle2, Clock3, FileText, MessageSquareQuote, TriangleAlert } from 'lucide-react'
import { cn } from '../../lib/cn'
import { spring } from '../ui/motion'
import type { AlertRecord } from '../../hooks/useSession'

function formatTimestamp(raw: string): string {
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return raw
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export type VoiceState = 'spoken' | 'speaking' | 'queued' | 'none'

function VoiceBadge({ state }: { state: VoiceState }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      {state === 'spoken' ? (
        <motion.span
          key="spoken"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={spring.snappy}
          className="inline-flex items-center gap-1.5 rounded-full border border-safe/40 bg-safe/10 px-3 py-1 text-[12px] font-semibold text-safe-text"
        >
          <CheckCircle2 size={14} strokeWidth={2} />
          Spoken verbatim
        </motion.span>
      ) : state === 'speaking' ? (
        <motion.span
          key="speaking"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="inline-flex items-center gap-2 rounded-full border border-voice-active/40 bg-voice-active/10 px-3 py-1 text-[12px] font-semibold text-voice-active-text"
        >
          <span className="flex h-3 items-end gap-[2px]" aria-hidden>
            {[0, 0.2, 0.1, 0.3].map((d) => (
              <span key={d} className="cc-anim-eq block h-3 w-[2px] rounded-full bg-current" style={{ animationDelay: `${d}s` }} />
            ))}
          </span>
          Reading the clause aloud&hellip;
        </motion.span>
      ) : state === 'queued' ? (
        <motion.span
          key="queued"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="inline-flex items-center gap-1.5 text-[12px] font-medium text-text-muted"
        >
          <Clock3 size={13} strokeWidth={1.75} />
          Voice correction queued
        </motion.span>
      ) : null}
    </AnimatePresence>
  )
}

/** Evidence card: what the rep said vs. what the signed contract literally
 * says. Aceternity Card Spotlight (cursor highlight via DOM mutation, no
 * re-render) + a severity ring that flares on arrival then settles.
 * Opaque by design: no glass on the proof surface. See THIRD_PARTY.md. */
export const AlertCard = memo(function AlertCard({ alert, isNewest, voice }: { alert: AlertRecord; isNewest: boolean; voice: VoiceState }) {
  const reducedMotion = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)

  function handleMouseMove(e: MouseEvent<HTMLDivElement>) {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    el.style.setProperty('--cc-spot-x', `${e.clientX - rect.left}px`)
    el.style.setProperty('--cc-spot-y', `${e.clientY - rect.top}px`)
  }

  return (
    <motion.article
      layout="position"
      initial={reducedMotion ? false : { opacity: 0, y: -20, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={spring.snappy}
      ref={ref}
      onMouseMove={handleMouseMove}
      className={cn(
        'group relative overflow-hidden rounded-lg border border-risk-high/35 bg-surface',
        'cc-alert-settled',
        isNewest && 'cc-anim-alert-ring',
      )}
    >
      <span className="absolute inset-y-0 left-0 w-[3px] bg-risk-high" aria-hidden />
      <div
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background:
            'radial-gradient(320px circle at var(--cc-spot-x, 50%) var(--cc-spot-y, 50%), color-mix(in oklab, var(--risk-high) 10%, transparent), transparent 70%)',
        }}
        aria-hidden
      />

      <header className="relative flex items-center justify-between gap-3 border-b border-border/60 px-5 py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-risk-high/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-risk-high-text">
            <TriangleAlert size={12} strokeWidth={2.25} />
            Contradiction
          </span>
          <span className="shrink-0 font-mono text-[13px] font-medium tabular-nums text-text-primary">§{alert.section_number}</span>
          <h3 className="truncate font-display text-[18px] font-semibold tracking-tight text-text-primary">{alert.title}</h3>
        </div>
        <time className="shrink-0 font-mono text-[12px] tabular-nums text-text-muted">{formatTimestamp(alert.t)}</time>
      </header>

      <div className={cn('relative grid px-5', isNewest ? 'gap-5 py-5' : 'gap-3 py-4')}>
        <div>
          <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
            <MessageSquareQuote size={12} strokeWidth={1.75} /> Rep said
          </p>
          <p className={cn('leading-relaxed text-text-secondary', isNewest ? 'text-[17px]' : 'text-[14px]')}>
            &ldquo;
            <span className="text-risk-high-text underline decoration-risk-high decoration-2 underline-offset-4">{alert.sentence}</span>
            &rdquo;
          </p>
        </div>

        <div>
          <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
            <FileText size={12} strokeWidth={1.75} /> Signed contract §{alert.section_number} says
          </p>
          <blockquote
            className={cn(
              'relative overflow-hidden rounded-md border border-l-2 bg-bg-sunken px-4 font-mono leading-relaxed text-text-primary transition-[border-color,box-shadow] duration-300',
              isNewest ? 'py-4 text-[18px]' : 'py-3 text-[14px]',
              voice === 'speaking'
                ? 'border-voice-active/40 border-l-voice-active shadow-[0_0_0_1px_color-mix(in_oklab,var(--voice-active)_20%,transparent),0_0_28px_-6px_color-mix(in_oklab,var(--voice-active)_45%,transparent)]'
                : 'border-border/70 border-l-text-primary/70',
            )}
          >
            &ldquo;{alert.literal_text}&rdquo;
            {/* indeterminate "being spoken" scan: no fake word timing, just liveness */}
            {voice === 'speaking' && <span className="cc-anim-scan pointer-events-none absolute inset-y-0 left-0 w-1/3" aria-hidden />}
          </blockquote>
        </div>
      </div>

      {voice !== 'none' && (
        <footer className="relative flex h-12 items-center border-t border-border/60 px-5">
          <VoiceBadge state={voice} />
        </footer>
      )}
    </motion.article>
  )
})

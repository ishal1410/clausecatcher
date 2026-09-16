import { useEffect } from 'react'
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { Quote } from 'lucide-react'
import type { Clause } from '../../lib/protocol'
import { Card, Chip } from '../ui'
import { duration, easing, spring } from '../ui/motion'

/** Seconds between clause cards landing. Slower than the shared staggerItem
 * (0.06) on purpose: this reveal is the setup screen's one authored moment,
 * and each card needs to read as individually extracted (spec §3). */
const STEP = 0.09

/** UI_SCREENS_SPEC.md §3 clause reveal. Choreography per card: rise in ->
 * a highlighter sweeps across the literal quote (we marked these exact words)
 * -> fades. The newest card keeps a rotating border-beam (Magic UI "Border
 * Beam" pattern, hand-rolled, see THIRD_PARTY.md) so the freshest extraction
 * reads as "just landed". Header count ticks up in lockstep with the cards. */
export default function ClauseList({ clauses }: { clauses: Clause[] }) {
  if (clauses.length === 0) return null
  const newestIndex = clauses.length - 1

  return (
    <section aria-labelledby="clauses-heading" className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="clauses-heading" className="text-[13px] font-medium text-text-secondary">
          <CountUp to={clauses.length} /> clause{clauses.length === 1 ? '' : 's'} extracted
        </h2>
        <span className="text-[12px] text-text-muted">quoted exactly as written</span>
      </div>
      <ul className="space-y-3">
        {clauses.map((clause, i) => (
          <motion.li
            key={clause.section_number}
            initial={{ opacity: 0, y: 14, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ ...spring.soft, delay: i * STEP, opacity: { duration: duration.slow, ease: easing.enter, delay: i * STEP } }}
          >
            <ClauseCard clause={clause} beam={i === newestIndex} sweepDelay={i * STEP + 0.18} />
          </motion.li>
        ))}
      </ul>
    </section>
  )
}

function CountUp({ to }: { to: number }) {
  const reduceMotion = useReducedMotion()
  const value = useMotionValue(reduceMotion ? to : 0)
  const rounded = useTransform(value, (v) => Math.round(v))

  useEffect(() => {
    const controls = animate(value, to, { duration: Math.min(to, 8) * STEP + 0.2, ease: easing.outExpo })
    return () => controls.stop()
  }, [to, value])

  return <motion.span className="tabular-nums text-text-primary">{rounded}</motion.span>
}

function ClauseCard({ clause, beam, sweepDelay }: { clause: Clause; beam: boolean; sweepDelay: number }) {
  const reduceMotion = useReducedMotion()
  const showBeam = beam && !reduceMotion

  return (
    <div
      className="relative overflow-hidden rounded-lg p-[1.5px]"
      style={
        showBeam
          ? {
              background: 'color-mix(in oklab, var(--brand) 28%, var(--border))',
              boxShadow: '0 10px 32px -14px color-mix(in oklab, var(--brand) 60%, transparent)',
            }
          : { background: 'var(--border)' }
      }
    >
      {showBeam && (
        <motion.div
          aria-hidden
          className="absolute left-1/2 top-1/2 aspect-square w-[160%] -translate-x-1/2 -translate-y-1/2"
          style={{
            background:
              'conic-gradient(from 0deg, transparent 0deg, transparent 210deg, var(--brand) 300deg, var(--brand-light) 340deg, var(--voice-active) 356deg, transparent 360deg)',
          }}
          animate={{ rotate: 360 }}
          transition={{ duration: 3.2, repeat: Infinity, ease: 'linear' }}
        />
      )}
      <Card className="relative rounded-[13px] border-0 px-4 py-3.5 sm:px-5">
        <div className="flex items-center gap-2.5">
          <Chip mono tone={beam ? 'brand' : 'neutral'} className="shrink-0">
            §{clause.section_number}
          </Chip>
          <h3 className="min-w-0 font-display text-[15px] leading-snug font-semibold text-text-primary">{clause.title}</h3>
        </div>
        <blockquote className="relative mt-3 overflow-hidden rounded-md border border-border/60 bg-bg-sunken py-2.5 pl-9 pr-3">
          {!reduceMotion && (
            // highlighter pass: clip-path wipe left -> right, hold, slow fade
            <motion.span
              aria-hidden
              className="absolute inset-0"
              style={{
                background:
                  'linear-gradient(90deg, color-mix(in oklab, var(--brand) 20%, transparent), color-mix(in oklab, var(--brand) 42%, transparent))',
              }}
              initial={{ clipPath: 'inset(0 100% 0 0)', opacity: 1 }}
              animate={{ clipPath: ['inset(0 100% 0 0)', 'inset(0 0% 0 0)', 'inset(0 0% 0 0)'], opacity: [1, 1, 0] }}
              transition={{ duration: 1.5, times: [0, 0.45, 1], ease: 'easeInOut', delay: sweepDelay }}
            />
          )}
          <Quote size={14} className="absolute left-3 top-3 text-brand-light/70" aria-hidden />
          <p className="relative font-mono text-[13px] leading-relaxed text-text-secondary">{clause.literal_text}</p>
        </blockquote>
      </Card>
    </div>
  )
}

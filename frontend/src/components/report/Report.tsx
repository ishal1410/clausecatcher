/**
 * Report — docs/UI_SCREENS_SPEC.md §5. The call's audit record: score ring,
 * contradiction timeline linked to the evidence cards below it, clauses the
 * call was checked against, facts row, export/new-session actions.
 *
 * Motion: one stagger cascade on mount (hero -> timeline -> clauses -> facts
 * -> actions); the score numeral and ring arc are driven by the SAME motion
 * value so they can never drift apart; the timeline sweep draws left-to-right
 * and each marker pops in as the sweep passes it; hovering/focusing a marker
 * or a card slides one shared selection outline between cards (layoutId).
 * MotionConfig reducedMotion="user" strips all transforms/layout moves for
 * users who ask for less motion, and the count-up jumps straight to the value.
 *
 * Severity is never color-only: verdict chip has a shield icon + words,
 * markers are numbered, flagged clause chips carry a triangle + "1 flag".
 */
import { useEffect, useId, useMemo, useState } from 'react'
import { MotionConfig, AnimatePresence, animate, motion, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { AlertCircle, Check, FileDown, RotateCcw, ShieldAlert, ShieldCheck, ShieldX, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Report as ReportData } from '../../lib/protocol'
import { Button, Card, Chip, duration, easing, rise, spring, stagger } from '../ui'
import type { ChipTone } from '../ui'
import { callSpan, flagsBySection, formatClock, positionPct, scoreBand, scoreOf } from './metrics'
import type { ScoreBand } from './metrics'

export interface ReportProps {
  report: ReportData | null
  error?: string | null
  onRetry?: () => void
  onNewSession: () => void
}

const bandStyle: Record<ScoreBand, { ring: string; text: string; chip: ChipTone; label: string; icon: ReactNode }> = {
  clean: { ring: 'var(--safe)', text: 'text-safe-text', chip: 'safe', label: 'Clean call', icon: <ShieldCheck size={13} aria-hidden /> },
  review: { ring: 'var(--brand-light)', text: 'text-brand-light', chip: 'brand', label: 'Needs review', icon: <ShieldAlert size={13} aria-hidden /> },
  risk: { ring: 'var(--risk-high)', text: 'text-risk-high-text', chip: 'risk-high', label: 'High risk', icon: <ShieldX size={13} aria-hidden /> },
}

const sectionTitle = 'font-display text-[18px] font-semibold tracking-[-0.01em] text-text-primary'

// -- score ring ------------------------------------------------------------

const R = 68
const CIRC = 2 * Math.PI * R
const TICK_R = 79
const TICKS = 60

function ScoreRing({ score, band }: { score: number; band: ScoreBand }) {
  const reduce = useReducedMotion()
  const value = useMotionValue(reduce ? score : 0)
  const rounded = useTransform(value, (v) => Math.round(v))
  const dashOffset = useTransform(value, (v) => CIRC * (1 - v / 100))
  const style = bandStyle[band]

  useEffect(() => {
    if (reduce) {
      value.set(score)
      return
    }
    const controls = animate(value, score, { duration: duration.count, ease: easing.outExpo, delay: 0.2 })
    return () => controls.stop()
  }, [score, reduce, value])

  const tickStep = (2 * Math.PI * TICK_R) / TICKS

  return (
    <div className="relative h-44 w-44 shrink-0" aria-hidden>
      {/* evidence-colored halo — the only glow on the page, and it encodes the band */}
      <div className="absolute inset-6 rounded-full opacity-25 blur-2xl" style={{ background: style.ring }} />
      <svg viewBox="0 0 176 176" className="relative h-full w-full -rotate-90">
        <circle cx="88" cy="88" r={TICK_R} fill="none" stroke="var(--border-strong)" strokeOpacity="0.55" strokeWidth="3" strokeDasharray={`1 ${tickStep - 1}`} />
        <circle cx="88" cy="88" r={R} fill="none" stroke="var(--border)" strokeOpacity="0.7" strokeWidth="8" />
        <motion.circle
          cx="88"
          cy="88"
          r={R}
          fill="none"
          stroke={style.ring}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={CIRC}
          style={{ strokeDashoffset: dashOffset }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={`flex items-baseline font-mono text-[44px] font-semibold leading-none tracking-[-0.04em] tabular-nums ${style.text}`}>
          <motion.span>{rounded}</motion.span>
          <span className="ml-0.5 text-[20px] font-medium tracking-normal text-text-muted">%</span>
        </span>
      </div>
    </div>
  )
}

function Hero({ report }: { report: ReportData }) {
  const score = scoreOf(report)
  const band = scoreBand(score, report.contradictions.length)
  const n = report.contradictions.length
  const { start, span } = callSpan(report)
  const started = new Date(start).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })

  const meta: Array<[string, string]> = [
    ['Duration', formatClock(span)],
    ['Started', started],
    ['Lines checked', String(report.transcript_count)],
  ]

  return (
    <motion.header variants={rise} className="flex flex-col items-center gap-8 text-center sm:flex-row sm:gap-12 sm:text-left">
      <ScoreRing score={score} band={band} />
      <div className="min-w-0 space-y-4">
        <Chip tone={bandStyle[band].chip} icon={bandStyle[band].icon}>
          {bandStyle[band].label}
        </Chip>
        <div className="space-y-2">
          <h1 id="report-title" className="font-display text-[40px] font-bold leading-[1.1] tracking-[-0.03em] text-text-primary">
            {score}% of lines on-contract
          </h1>
          <p className="text-[15px] leading-relaxed text-text-secondary">
            {n === 0 ? 'No contradictions' : `${n} contradiction${n === 1 ? '' : 's'}`} caught out of {report.transcript_count} lines.
          </p>
        </div>
        <dl className="flex flex-wrap justify-center gap-x-6 gap-y-2 sm:justify-start">
          {meta.map(([k, v]) => (
            <div key={k} className="flex items-baseline gap-2">
              <dt className="text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">{k}</dt>
              <dd className="font-mono text-[13px] tabular-nums text-text-secondary">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </motion.header>
  )
}

// -- timeline --------------------------------------------------------------

type Contradiction = ReportData['contradictions'][number]

function ContradictionCard({ c, index, clock }: { c: Contradiction; index: number; clock: string }) {
  return (
    <Card className="overflow-hidden p-5 pl-6">
      {/* inset severity bar — a straight bar, not a border-left bent around the corner radius */}
      <span className="absolute inset-y-5 left-0 w-[3px] rounded-r-full bg-risk-high" aria-hidden />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-[12px] tabular-nums text-text-muted">{String(index + 1).padStart(2, '0')}</span>
          <Chip tone="risk-high" mono icon={<TriangleAlert size={12} aria-hidden />}>
            §{c.section_number}
          </Chip>
        </div>
        <span className="font-mono text-[12px] tabular-nums text-text-muted">
          <span className="sr-only">At </span>
          {clock}
          <span> into call</span>
        </span>
      </div>

      <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">Rep said</p>
      <p className="mt-1 text-[15px] leading-relaxed text-text-secondary">&ldquo;{c.sentence}&rdquo;</p>

      <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">Contract §{c.section_number} says</p>
      <blockquote className="mt-1.5 rounded-md border border-border/60 bg-bg-sunken px-4 py-3 font-mono text-[14px] leading-relaxed text-text-primary">
        &ldquo;{c.literal_text}&rdquo;
      </blockquote>
    </Card>
  )
}

function Timeline({ report }: { report: ReportData }) {
  const reduce = useReducedMotion()
  const baseId = useId()
  const [active, setActive] = useState<number | null>(null)
  const { start, span } = callSpan(report)
  const items = report.contradictions.map((c, i) => {
    const pct = positionPct(c.t, start, span)
    return { c, i, pct, clock: formatClock((pct / 100) * span) }
  })
  const cardId = (i: number) => `${baseId}-contradiction-${i}`

  function jumpTo(i: number) {
    setActive(i)
    document.getElementById(cardId(i))?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' })
  }

  const empty = items.length === 0

  return (
    <motion.section variants={rise} aria-labelledby={`${baseId}-title`} className="space-y-5">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id={`${baseId}-title`} className={sectionTitle}>
          Contradiction timeline
        </h2>
        <span className="font-mono text-[12px] tabular-nums text-text-muted">
          {empty ? 'none flagged' : `${items.length} flagged`}
        </span>
      </div>

      <div className="px-3.5 pt-4">
        <div className="relative h-11">
          <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 rounded-full bg-border/70" />
          {/* playback sweep: scaleX, never width */}
          <motion.div
            className={`absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 origin-left rounded-full ${empty ? 'bg-safe' : 'bg-text-muted/45'}`}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: duration.count, ease: easing.outExpo, delay: 0.35 }}
          />
          {empty && (
            <span className="absolute right-0 top-1/2 grid h-6 w-6 -translate-y-1/2 translate-x-1/2 place-items-center rounded-full border border-safe/50 bg-bg-base text-safe-text">
              <Check size={13} aria-hidden />
            </span>
          )}
          {items.map(({ c, i, pct, clock }) => {
            const on = active === i
            return (
              <button
                key={i}
                type="button"
                data-timeline-marker
                aria-label={`Contradiction ${i + 1}, section ${c.section_number}, at ${clock}`}
                aria-controls={cardId(i)}
                onClick={() => jumpTo(i)}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                style={{ left: `${pct}%` }}
                className="group absolute top-1/2 grid h-9 w-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full focus-visible:outline-none"
              >
                {/* motion owns the one-time pop-in (transform); hover scale is the CSS `scale` property, so they compose */}
                <motion.span
                  initial={{ opacity: 0, scale: 0.4 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ ...spring.snappy, delay: reduce ? 0 : 0.35 + (pct / 100) * duration.count * 0.6 }}
                  className={`grid h-6 w-6 place-items-center rounded-full border font-mono text-[11px] font-semibold tabular-nums transition-[background-color,border-color,color,scale,box-shadow] duration-150 group-focus-visible:ring-2 group-focus-visible:ring-voice-active group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-bg-base ${
                    on
                      ? 'scale-[1.15] border-risk-high bg-risk-high text-white shadow-[0_0_0_4px_rgba(239,68,68,0.18)] motion-reduce:scale-100'
                      : 'border-risk-high/70 bg-bg-base text-risk-high-text'
                  }`}
                >
                  {i + 1}
                </motion.span>
                <AnimatePresence>
                  {on && (
                    <motion.span
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0, transition: spring.snappy }}
                      exit={{ opacity: 0, transition: { duration: duration.instant } }}
                      className="pointer-events-none absolute bottom-full mb-1 whitespace-nowrap rounded-md border border-border bg-surface px-2 py-1 font-mono text-[11px] tabular-nums text-text-secondary shadow-card"
                      aria-hidden
                    >
                      §{c.section_number} · {clock}
                    </motion.span>
                  )}
                </AnimatePresence>
              </button>
            )
          })}
        </div>
        <div className="flex justify-between font-mono text-[11px] tabular-nums text-text-muted" aria-hidden>
          <span>00:00</span>
          <span>{formatClock(span)}</span>
        </div>
      </div>

      {empty ? (
        <p className="flex items-center gap-2 text-[14px] text-safe-text">
          <ShieldCheck size={16} aria-hidden /> No contradictions in this call.
        </p>
      ) : (
        <motion.ol variants={stagger} className="space-y-3">
          {items.map(({ c, i, clock }) => (
            <motion.li
              key={i}
              id={cardId(i)}
              variants={rise}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
              className="print-avoid-break relative scroll-mt-24"
            >
              {active === i && (
                <motion.div
                  layoutId={`${baseId}-selection`}
                  transition={spring.layout}
                  className="pointer-events-none absolute -inset-1.5 rounded-[20px] border border-risk-high/35 bg-risk-high/[0.03]"
                  aria-hidden
                />
              )}
              <ContradictionCard c={c} index={i} clock={clock} />
            </motion.li>
          ))}
        </motion.ol>
      )}
    </motion.section>
  )
}

// -- clauses + facts -------------------------------------------------------

function Clauses({ report }: { report: ReportData }) {
  const baseId = useId()
  const flags = useMemo(() => flagsBySection(report), [report])
  const sections = useMemo(() => [...new Set([...report.contract_clauses_referenced, ...flags.keys()])], [report, flags])
  if (sections.length === 0) return null

  return (
    <motion.section variants={rise} aria-labelledby={baseId} className="space-y-3">
      <h2 id={baseId} className={sectionTitle}>
        Clauses checked
      </h2>
      <p className="text-[14px] text-text-muted">Every clause this call was measured against. Flagged ones were contradicted at least once.</p>
      <motion.ul variants={stagger} className="flex flex-wrap gap-2 pt-1">
        {sections.map((s) => {
          const count = flags.get(s) ?? 0
          return (
            <motion.li key={s} variants={rise}>
              {count > 0 ? (
                <Chip tone="risk-high" mono icon={<TriangleAlert size={12} aria-hidden />}>
                  §{s} · {count} flag{count === 1 ? '' : 's'}
                </Chip>
              ) : (
                <Chip tone="neutral" mono icon={<Check size={12} className="text-safe-text" aria-hidden />}>
                  §{s} · held
                </Chip>
              )}
            </motion.li>
          )
        })}
      </motion.ul>
    </motion.section>
  )
}

function Facts({ report }: { report: ReportData }) {
  const baseId = useId()
  const errors = report.claim_check_errors
  const tiles: Array<{ label: string; value: string; warn?: boolean }> = [
    { label: 'Est. cost', value: `$${report.est_cost_usd.toFixed(4)}` },
    { label: 'Claim checks', value: String(report.claim_check_calls) },
    { label: 'Check errors', value: String(errors), warn: errors > 0 },
    { label: 'Transcript lines', value: String(report.transcript_count) },
  ]
  return (
    <motion.section variants={rise} aria-labelledby={baseId} className="space-y-3">
      <h2 id={baseId} className={sectionTitle}>
        Call facts
      </h2>
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border shadow-card sm:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.label} className="flex flex-col-reverse gap-1.5 bg-surface px-5 py-4">
            <dt className="text-[11px] font-semibold uppercase tracking-[0.05em] text-text-muted">{t.label}</dt>
            <dd
              className={`flex items-center gap-1.5 font-mono text-[22px] font-medium leading-none tracking-[-0.02em] tabular-nums ${
                t.warn ? 'text-risk-medium-text' : 'text-text-primary'
              }`}
            >
              {t.value}
              {t.warn && <AlertCircle size={15} aria-hidden />}
            </dd>
          </div>
        ))}
      </dl>
    </motion.section>
  )
}

// -- states ----------------------------------------------------------------

function ReportSkeleton() {
  return (
    <div role="status" aria-label="Loading call report" className="animate-pulse space-y-14">
      <div className="flex flex-col items-center gap-8 sm:flex-row sm:gap-12">
        <div className="h-44 w-44 shrink-0 rounded-full border-8 border-surface" />
        <div className="w-full max-w-sm space-y-4">
          <div className="mx-auto h-6 w-28 rounded-full bg-surface sm:mx-0" />
          <div className="mx-auto h-10 w-64 rounded-md bg-surface sm:mx-0" />
          <div className="mx-auto h-4 w-56 rounded bg-surface sm:mx-0" />
        </div>
      </div>
      <div className="space-y-4">
        <div className="h-5 w-48 rounded bg-surface" />
        <div className="h-0.5 rounded-full bg-surface" />
        <div className="h-32 rounded-lg bg-surface" />
      </div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-border sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-[74px] bg-surface" />
        ))}
      </div>
    </div>
  )
}

const shell = 'mx-auto max-w-3xl px-4 py-16 sm:px-6 sm:py-24'

export function Report({ report, error, onRetry, onNewSession }: ReportProps) {
  let body: ReactNode
  if (error) {
    body = (
      <div className={shell}>
        <Card role="alert" className="mx-auto max-w-md space-y-4 p-8 text-center">
          <AlertCircle size={22} className="mx-auto text-risk-high-text" aria-hidden />
          <h1 className="font-display text-[20px] font-semibold text-text-primary">Couldn&rsquo;t load the call report</h1>
          <p className="text-[14px] leading-relaxed text-risk-high-text">{error}</p>
          {onRetry && (
            <Button onClick={onRetry}>
              <RotateCcw size={16} aria-hidden /> Retry
            </Button>
          )}
        </Card>
      </div>
    )
  } else if (!report) {
    body = (
      <div className={shell}>
        <ReportSkeleton />
      </div>
    )
  } else {
    body = (
      <motion.article variants={stagger} initial="hidden" animate="show" aria-labelledby="report-title" className={`${shell} space-y-14`}>
        <Hero report={report} />
        <Timeline report={report} />
        <Clauses report={report} />
        <Facts report={report} />
        <motion.footer
          variants={rise}
          className="flex flex-col-reverse gap-3 border-t border-border pt-8 sm:flex-row sm:items-center sm:justify-between print:hidden"
        >
          <Button variant="secondary" onClick={() => window.print()} className="w-full sm:w-auto">
            <FileDown size={16} aria-hidden /> Export PDF
          </Button>
          <Button onClick={onNewSession} className="w-full sm:w-auto">
            <RotateCcw size={16} aria-hidden /> Start a new session
          </Button>
        </motion.footer>
      </motion.article>
    )
  }
  return <MotionConfig reducedMotion="user">{body}</MotionConfig>
}

export default Report

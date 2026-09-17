/**
 * Landing.tsx — ClauseCatcher marketing page (wave 2).
 *
 * Page arc: hero (the product catching a contradiction, looping) -> the
 * problem, scrubbed in word by word -> how the pipeline works -> who buys it
 * and what risk it removes -> closing CTA.
 *
 * All contract text on this page is the real demo contract the backend loads
 * (spikes/harness/fake_contract.json), and the spoken-alert string matches
 * server/voice.py, so the marketing page never shows a clause the product
 * would not actually quote.
 *
 * Reuses components/ui primitives + index.css tokens. Display sizes follow
 * DESIGN_SYSTEM.md display-xl/lg/md (40/28/20px), applied locally.
 */
import { useEffect, useRef, useState } from 'react'
import type { PointerEvent, ReactNode } from 'react'
import {
  AnimatePresence,
  animate,
  motion,
  useInView,
  useMotionTemplate,
  useMotionValue,
  useReducedMotion,
  useScroll,
  useTransform,
} from 'motion/react'
import type { MotionValue } from 'motion/react'
import { ArrowUpRight, CheckCircle2, FileText, Quote, ShieldCheck, Users } from 'lucide-react'
import { Button, Card, Chip, StatusDot, duration, easing, spring } from '../ui'
import type { CardProps } from '../ui'
import { cn } from '../../lib/cn'

/* Demo contract (verbatim from spikes/harness/fake_contract.json) */
const CLAUSES = [
  {
    section: '3.1',
    title: 'Pricing & Seat Cap',
    text: 'Flat $48,000 up to 50 seats; extra seats need signed written amendment; no automatic or verbal discounting.',
  },
  {
    section: '4.2',
    title: 'Renewal',
    text: 'Auto-renews 12 months unless written notice 60 days before term ends; no mid-term termination.',
  },
  { section: '5.3', title: 'Data Retention', text: '30-day recoverable archive then permanent deletion.' },
  {
    section: '6.1',
    title: 'Support SLA',
    text: 'P1 within 4 business hours Mon-Fri 9-6 ET; 24/7 requires Premium Support Addendum.',
  },
]
const PRICING = CLAUSES[0]

export default function Landing({ onStart }: { onStart: () => void }) {
  return (
    <div className="relative min-h-[100dvh] w-full overflow-x-clip bg-bg-base text-text-primary antialiased">
      <NavBar onStart={onStart} />
      <main>
        <Hero onStart={onStart} />
        <ProblemStatement />
        <HowItWorks />
        <WhoItsFor />
        <ClosingCta onStart={onStart} />
      </main>
      <footer className="border-t border-border/60 px-6 py-8 text-center text-[13px] text-text-muted">
        ClauseCatcher, built for the AssemblyAI Voice Agent Hackathon.
      </footer>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Nav — the one place translucent "liquid glass" chrome is allowed    */
/* ------------------------------------------------------------------ */

function NavBar({ onStart }: { onStart: () => void }) {
  return (
    <header className="fixed inset-x-0 z-20 flex justify-center px-4" style={{ top: 'max(1rem, env(safe-area-inset-top, 0px))' }}>
      <Card
        glass
        role="navigation"
        aria-label="Primary"
        className="flex w-full max-w-3xl items-center justify-between gap-4 rounded-full px-3 py-2 sm:px-4"
      >
        <a
          href="#top"
          className="flex items-center gap-2.5 rounded-full px-1.5 py-1 font-display text-[15px] font-bold tracking-tight text-text-primary"
        >
          <LogoMark />
          ClauseCatcher
        </a>
        <CtaButton onClick={onStart} size="sm" label="Try the live demo" />
      </Card>
    </header>
  )
}

/** Section mark inside a speech-bubble corner: "a clause, spoken". */
function LogoMark() {
  return (
    <span aria-hidden="true" className="grid h-7 w-7 place-items-center rounded-[9px] rounded-bl-[3px] bg-brand-strong font-mono text-[14px] font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.18)]">
      §
    </span>
  )
}

function CtaButton({ onClick, label, size = 'md' }: { onClick: () => void; label: string; size?: 'sm' | 'md' | 'lg' }) {
  const lg = size === 'lg'
  return (
    <Button
      variant="primary"
      size={lg ? 'md' : size}
      onClick={onClick}
      className={cn('group rounded-full pr-1.5', size === 'sm' ? 'pl-4' : 'pl-6', lg && 'h-12 pl-7 text-base')}
    >
      {label}
      <span
        aria-hidden="true"
        className={cn(
          'grid place-items-center rounded-full bg-white/15 transition-transform duration-200 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:-translate-y-px group-hover:translate-x-0.5',
          size === 'sm' ? 'h-6 w-6' : lg ? 'h-9 w-9' : 'h-7 w-7',
        )}
      >
        <ArrowUpRight size={size === 'sm' ? 13 : 16} strokeWidth={2} />
      </span>
    </Button>
  )
}

/* ------------------------------------------------------------------ */
/* Spotlight card — pointer-tracked radial light (Aceternity-style)    */
/* Motion values only, so pointer moves never re-render React.         */
/* ------------------------------------------------------------------ */

function SpotlightCard({ className, children, ...props }: CardProps) {
  const mx = useMotionValue(-600)
  const my = useMotionValue(-600)
  const light = useMotionTemplate`radial-gradient(420px circle at ${mx}px ${my}px, rgba(129,140,248,0.11), transparent 65%)`
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    mx.set(e.clientX - r.left)
    my.set(e.clientY - r.top)
  }
  return (
    <Card {...props} onPointerMove={onPointerMove} className={cn('group overflow-hidden', className)}>
      <motion.div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: light }}
      />
      {children}
    </Card>
  )
}

/* ------------------------------------------------------------------ */
/* Hero                                                                */
/* ------------------------------------------------------------------ */

function scrollToId(id: string, reduceMotion: boolean | null) {
  document.getElementById(id)?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
}

function Hero({ onStart }: { onStart: () => void }) {
  const reduceMotion = useReducedMotion()
  return (
    <section id="top" className="relative flex min-h-[100dvh] items-center overflow-hidden px-6 pb-20 pt-28 sm:pt-32">
      <ContractField />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_55%_45%_at_75%_40%,rgba(79,70,229,0.16),transparent_70%)]"
      />

      <div className="relative mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-14 lg:grid-cols-12 lg:gap-12">
        <div className="lg:col-span-7">
          <h1 className="font-display text-[clamp(2rem,4.6vw,3.75rem)] font-bold leading-[1.04] tracking-[-0.035em] text-balance text-text-primary">
            <span className="block">Your reps go off-script.</span>
            <span className="block">Your contract doesn&rsquo;t.</span>
          </h1>

          <p className="mt-6 max-w-[34rem] text-lg leading-relaxed text-pretty text-text-secondary">
            ClauseCatcher listens to live sales calls, catches any line that contradicts the signed contract,
            and reads the exact clause aloud while the customer is still on the line.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <CtaButton onClick={onStart} label="Try the live demo" />
            <a
              href="#how-it-works"
              onClick={(e) => {
                e.preventDefault()
                scrollToId('how-it-works', reduceMotion)
              }}
              className="inline-flex h-10 items-center rounded-full px-4 text-[15px] font-medium text-text-secondary transition-colors hover:bg-surface hover:text-text-primary"
            >
              How it works
            </a>
          </div>

          <p className="mt-12 max-w-md text-[13px] leading-relaxed text-text-muted">
            Runs on AssemblyAI Streaming STT and the AssemblyAI Voice Agent, with Gemini checking each sentence
            against your contract.
          </p>
        </div>

        <div className="lg:col-span-5">
          <CockpitPreview />
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Hero background — the demo contract itself, with a slow scan line   */
/* that brightens the text it passes. Replaces wave 1's generic canvas */
/* "hyperdrive": the backdrop is the thing being enforced.             */
/* Transform-only animation; static under reduced motion; pauses in    */
/* hidden tabs.                                                        */
/* ------------------------------------------------------------------ */

const SCAN_BAND = 220

function ContractText({ lit }: { lit: boolean }) {
  const rows = Array.from({ length: 5 }, () => CLAUSES).flat()
  return (
    <div
      className={cn(
        'absolute inset-x-0 top-0 columns-2 gap-14 px-6 pt-24 font-mono text-[13px] leading-7',
        lit ? 'text-text-primary/30' : 'text-text-primary/[0.06]',
      )}
    >
      {rows.map((c, i) => {
        const cut = c.text.indexOf('no automatic or verbal discounting')
        return (
          <p key={i} className="mb-5 break-inside-avoid">
            <span className={lit ? 'text-brand-light/70' : undefined}>
              §{c.section} {c.title}.
            </span>{' '}
            {cut === -1 ? (
              c.text
            ) : (
              <>
                {c.text.slice(0, cut)}
                <span className={lit ? 'text-risk-high-text' : 'text-risk-high/25'}>{c.text.slice(cut)}</span>
              </>
            )}
          </p>
        )
      })}
    </div>
  )
}

function ContractField() {
  const reduceMotion = useReducedMotion()
  const fieldRef = useRef<HTMLDivElement>(null)
  const y = useMotionValue(-SCAN_BAND)
  const counterY = useTransform(y, (v) => -v)

  useEffect(() => {
    const el = fieldRef.current
    if (!el || reduceMotion) return
    let controls: ReturnType<typeof animate> | undefined
    const ro = new ResizeObserver(() => {
      controls?.stop()
      controls = animate(y, [-SCAN_BAND, el.offsetHeight], {
        duration: 9,
        ease: 'linear',
        repeat: Infinity,
        repeatDelay: 1.5,
      })
    })
    ro.observe(el)
    const onVisibility = () => (document.hidden ? controls?.pause() : controls?.play())
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      controls?.stop()
      ro.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [reduceMotion, y])

  return (
    <div
      ref={fieldRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-y-0 left-[calc(50%+3rem)] right-0 hidden select-none overflow-hidden [mask-image:radial-gradient(ellipse_70%_75%_at_60%_45%,#000_25%,transparent_78%)] lg:block"
    >
      <ContractText lit={false} />
      {!reduceMotion && (
        <motion.div
          className="absolute inset-x-0 top-0 overflow-hidden [mask-image:linear-gradient(to_bottom,transparent,#000_85%)]"
          style={{ y, height: SCAN_BAND }}
        >
          <motion.div className="absolute inset-0" style={{ y: counterY }}>
            <ContractText lit />
          </motion.div>
          <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-brand-light/70 to-transparent" />
        </motion.div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Cockpit preview — scripted loop of the product's core moment.       */
/* Rep line types in -> offending words underline -> alert card quotes */
/* the literal clause -> words light up in sync as the Voice Agent     */
/* speaks them -> "Spoken verbatim". No network calls.                 */
/* ------------------------------------------------------------------ */

const REP_LINE = 'We can also do a verbal discount for a big client.'
const HIGHLIGHT_PHRASE = 'verbal discount'
const CLAUSE_WORDS = PRICING.text.split(' ')
const TYPE_MS = 26
const WORD_S = 0.15

type PreviewStep = 'typing' | 'highlight' | 'alert' | 'speaking' | 'verified' | 'exit'

function CockpitPreview() {
  const reduceMotion = useReducedMotion()
  const wrapRef = useRef<HTMLDivElement>(null)
  const inView = useInView(wrapRef, { amount: 0.4 })
  const [typed, setTyped] = useState(reduceMotion ? REP_LINE : '')
  const [step, setStep] = useState<PreviewStep>(reduceMotion ? 'verified' : 'typing')
  const [cycle, setCycle] = useState(0)

  useEffect(() => {
    if (reduceMotion || !inView) return
    const timers: number[] = []
    const typeMs = REP_LINE.length * TYPE_MS
    const speakMs = CLAUSE_WORDS.length * WORD_S * 1000 + 450

    setTyped('')
    setStep('typing')
    let i = 0
    const typeInterval = window.setInterval(() => {
      i += 1
      setTyped(REP_LINE.slice(0, i))
      if (i >= REP_LINE.length) window.clearInterval(typeInterval)
    }, TYPE_MS)

    const at = (ms: number, fn: () => void) => timers.push(window.setTimeout(fn, ms))
    at(typeMs + 150, () => setStep('highlight'))
    at(typeMs + 450, () => setStep('alert'))
    at(typeMs + 1050, () => setStep('speaking'))
    at(typeMs + 1050 + speakMs, () => setStep('verified'))
    at(typeMs + 1050 + speakMs + 2600, () => setStep('exit'))
    at(typeMs + 1050 + speakMs + 3200, () => setCycle((c) => c + 1))

    return () => {
      window.clearInterval(typeInterval)
      timers.forEach((t) => window.clearTimeout(t))
    }
  }, [inView, reduceMotion, cycle])

  const showHighlight = step !== 'typing'
  const showAlert = step === 'alert' || step === 'speaking' || step === 'verified'
  const speaking = step === 'speaking'
  const verified = step === 'verified'

  return (
    <div
      ref={wrapRef}
      className="relative mx-auto w-full max-w-[31rem]"
      role="img"
      aria-label="Preview: a rep offers a verbal discount, ClauseCatcher flags it against section 3.1 of the contract and reads the clause aloud word for word."
    >
      <div aria-hidden="true" className="absolute -inset-10 -z-10 rounded-[3rem] bg-[radial-gradient(closest-side,rgba(239,68,68,0.10),transparent)]" />
      <motion.div animate={{ opacity: step === 'exit' ? 0 : 1 }} transition={{ duration: duration.slow, ease: easing.standard }}>
        <SpotlightCard className="rounded-2xl p-5 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.7)] sm:p-6">
          <div className="relative flex items-center justify-between">
            <StatusDot label="Live call" tone="live" pulse />
            <span className="text-[12px] text-text-muted">Demo contract, 4 clauses</span>
          </div>

          <div className="relative mt-5 space-y-3 font-mono text-[13px] leading-relaxed">
            <p className="flex gap-3 text-text-muted">
              <span className="w-8 shrink-0 text-text-muted/70 tabular-nums">Rep</span>
              <span className="min-w-0">
                Seats are capped at fifty on this plan.
                <CheckCircle2 size={13} className="ml-1.5 inline -translate-y-px text-safe-text" aria-hidden="true" />
              </span>
            </p>
            <p className="flex min-h-[3rem] gap-3 text-text-primary">
              <span className="w-8 shrink-0 text-text-muted/70">Rep</span>
              <span className="min-w-0">
                {renderHighlightedLine(typed, showHighlight)}
                {step === 'typing' && (
                  <span className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse bg-text-muted" aria-hidden="true" />
                )}
              </span>
            </p>
          </div>

          <div className="relative mt-5 min-h-[12.75rem]">
            <motion.div
              aria-hidden="true"
              className="absolute inset-0 flex items-center justify-center gap-2 rounded-xl border border-dashed border-border text-[13px] text-text-muted"
              animate={{ opacity: showAlert ? 0 : 1 }}
              transition={{ duration: duration.base }}
            >
              <ShieldCheck size={15} strokeWidth={1.5} />
              Checking each sentence against the contract
            </motion.div>
            <AnimatePresence>
              {showAlert && (
                <motion.div
                  key={cycle}
                  initial={{ opacity: 0, scale: 0.96, y: 14 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={spring.snappy}
                >
                  <Card glow="risk-high" className="rounded-xl p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <Chip tone="risk-high" icon={<Quote size={12} aria-hidden="true" />} className="normal-case tracking-normal">
                        Contradicts §{PRICING.section}
                      </Chip>
                      <span className="text-[12px] text-text-muted">{PRICING.title}</span>
                    </div>

                    <p className="mt-3 rounded-lg border border-border bg-bg-sunken px-3.5 py-3 font-mono text-[13px] leading-relaxed text-text-primary">
                      <span aria-hidden="true">&ldquo;</span>
                      {CLAUSE_WORDS.map((w, i) => (
                        <motion.span
                          key={i}
                          initial={false}
                          animate={{ opacity: speaking || verified ? 1 : 0.55 }}
                          transition={{ duration: duration.base, delay: speaking ? i * WORD_S : 0 }}
                        >
                          {w}
                          {i < CLAUSE_WORDS.length - 1 ? ' ' : ''}
                        </motion.span>
                      ))}
                      <span aria-hidden="true">&rdquo;</span>
                    </p>

                    <div className="mt-3 flex min-h-7 items-center justify-between gap-3">
                      <div className="flex items-center gap-2.5">
                        <VoiceBars active={speaking} />
                        <span className="text-[12px] text-text-muted">
                          {speaking ? 'Reading the clause aloud…' : verified ? 'Read aloud' : 'Voice Agent'}
                        </span>
                      </div>
                      <AnimatePresence>
                        {verified && (
                          <motion.div
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: duration.fast, ease: easing.standard }}
                          >
                            <Chip tone="safe" icon={<CheckCircle2 size={12} aria-hidden="true" />} className="normal-case tracking-normal">
                              Spoken verbatim
                            </Chip>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </Card>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </SpotlightCard>
      </motion.div>
    </div>
  )
}

function renderHighlightedLine(text: string, highlightOn: boolean) {
  const idx = text.indexOf(HIGHLIGHT_PHRASE)
  if (!highlightOn || idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <span className="relative text-risk-high-text">
        {text.slice(idx, idx + HIGHLIGHT_PHRASE.length)}
        <motion.span
          aria-hidden="true"
          className="absolute inset-x-0 -bottom-0.5 h-[2px] origin-left rounded-full bg-risk-high"
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.3, ease: easing.outExpo }}
        />
      </span>
      {text.slice(idx + HIGHLIGHT_PHRASE.length)}
    </>
  )
}

function VoiceBars({ active }: { active: boolean }) {
  const reduceMotion = useReducedMotion()
  const heights = [7, 14, 9, 16, 8]
  return (
    <div className="flex h-4 items-end gap-[3px]" aria-hidden="true">
      {heights.map((h, i) => (
        <motion.span
          key={i}
          className="w-[3px] rounded-full bg-voice-active"
          initial={{ height: 3 }}
          animate={active && !reduceMotion ? { height: [3, h, 4, h * 0.7, 3] } : { height: active ? h * 0.5 : 3 }}
          transition={active && !reduceMotion ? { duration: 0.9, repeat: Infinity, ease: easing.standard, delay: i * 0.08 } : { duration: 0.2 }}
        />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Problem statement — words scrub from dim to full as you scroll      */
/* ------------------------------------------------------------------ */

const PROBLEM =
  'A rep promises a discount the contract forbids. Usually someone finds it later, on a call recording, after the customer is already counting on it. ClauseCatcher catches it while the customer is still on the line.'

function ProblemStatement() {
  const reduceMotion = useReducedMotion()
  const ref = useRef<HTMLParagraphElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 0.85', 'end 0.5'] })
  const words = PROBLEM.split(' ')

  return (
    <section aria-label="The problem" className="px-6 py-32 md:py-44">
      <p
        ref={ref}
        className="mx-auto max-w-5xl font-display text-[clamp(1.75rem,3.6vw,3rem)] font-semibold leading-[1.18] tracking-[-0.02em] text-text-primary"
      >
        {reduceMotion
          ? PROBLEM
          : words.map((w, i) => (
              <ScrubWord key={i} progress={scrollYProgress} range={[i / words.length, (i + 1) / words.length]}>
                {w}
              </ScrubWord>
            ))}
      </p>
    </section>
  )
}

function ScrubWord({ progress, range, children }: { progress: MotionValue<number>; range: [number, number]; children: string }) {
  const opacity = useTransform(progress, range, [0.16, 1])
  return (
    <>
      <motion.span style={{ opacity }}>{children}</motion.span>{' '}
    </>
  )
}

/* ------------------------------------------------------------------ */
/* How it works — three stages, a signal sweep lights each node        */
/* (pattern after Magic UI Animated Beam, MIT; transform/opacity only) */
/* ------------------------------------------------------------------ */

const PIPELINE: { label: string; vendor: string; caption: string; artifact: ReactNode }[] = [
  {
    label: 'Streaming transcription',
    vendor: 'AssemblyAI Streaming STT',
    caption: 'The rep’s words are transcribed as they speak, sentence by sentence.',
    artifact: (
      <span className="text-text-secondary">
        we can also do a <span className="text-risk-high-text">verbal discount</span> for a big client
      </span>
    ),
  },
  {
    label: 'Contradiction check',
    vendor: 'Gemini',
    caption: 'Each finished sentence is checked against every clause in the signed contract.',
    artifact: (
      <span className="grid grid-cols-[auto_1fr] gap-x-4 text-text-muted">
        <span>verdict</span>
        <span className="text-risk-high-text">contradiction</span>
        <span>clause_id</span>
        <span className="text-text-primary">3.1</span>
      </span>
    ),
  },
  {
    label: 'Spoken correction',
    vendor: 'AssemblyAI Voice Agent',
    caption: 'The literal clause text is read aloud, fetched by section, never written by a model.',
    artifact: (
      <span className="text-text-secondary">
        &ldquo;Contract alert: section 3.1 says: {PRICING.text}&rdquo;
      </span>
    ),
  },
]

const SWEEP_S = 3.6
const SWEEP_END = 0.7 // fraction of the cycle at which the sweep reaches the last node

function HowItWorks() {
  const reduceMotion = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { amount: 0.3 })
  const animateSweep = inView && !reduceMotion

  return (
    <section id="how-it-works" aria-labelledby="how-it-works-heading" className="scroll-mt-20 px-6 py-32 md:py-44">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <h2 id="how-it-works-heading" className="font-display text-[28px] font-bold leading-[1.2] tracking-[-0.02em] text-balance text-text-primary md:text-[40px] md:leading-[1.15]">
            From a spoken sentence to a cited clause
          </h2>
          <p className="mt-4 text-[17px] leading-relaxed text-text-secondary">
            Three stages run for every sentence a rep finishes. Nothing waits for the call to end.
          </p>
        </div>

        <div ref={ref} className="relative mt-16 md:mt-20">
          {/* connector: from node 1 centre to node 3 centre (cols = (100% - 2 gaps) / 3) */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute top-[22px] hidden h-px md:block"
            style={{ left: '22px', width: 'calc((100% - 4rem) * 2 / 3 + 4rem)' }}
          >
            <div className="absolute inset-0 bg-border" />
            {animateSweep && (
              <motion.div
                className="absolute inset-0 origin-left bg-gradient-to-r from-brand/0 via-brand-light to-voice-active shadow-[0_0_12px_rgba(129,140,248,0.8)]"
                initial={{ scaleX: 0, opacity: 1 }}
                animate={{ scaleX: [0, 1, 1, 1], opacity: [1, 1, 1, 0] }}
                transition={{ duration: SWEEP_S, times: [0, SWEEP_END, 0.85, 1], ease: 'linear', repeat: Infinity }}
              />
            )}
          </div>

          <ol className="grid grid-cols-1 gap-12 md:grid-cols-3 md:gap-8">
            {PIPELINE.map((step, i) => {
              const t = (SWEEP_END * i) / (PIPELINE.length - 1)
              return (
                <li key={step.label} className="flex flex-col">
                  <div className="relative grid h-11 w-11 place-items-center rounded-full border border-border-strong bg-bg-raised font-mono text-sm font-medium text-brand-light">
                    <span aria-hidden="true">{i + 1}</span>
                    {animateSweep && (
                      <motion.span
                        aria-hidden="true"
                        className="absolute -inset-px rounded-full border border-brand-light shadow-[0_0_18px_rgba(129,140,248,0.55)]"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: [0, 0, 1, 0] }}
                        transition={{ duration: SWEEP_S, times: [0, t, Math.min(t + 0.03, 1), Math.min(t + 0.3, 1)], repeat: Infinity }}
                      />
                    )}
                  </div>
                  <h3 className="mt-6 font-display text-xl font-semibold leading-[1.3] text-text-primary">{step.label}</h3>
                  <p className="mt-1 font-mono text-[12px] text-brand-light">{step.vendor}</p>
                  <p className="mt-3 text-[15px] leading-relaxed text-text-muted">{step.caption}</p>
                  <div className="mt-6 flex-1 rounded-lg border border-border bg-bg-sunken px-4 py-3 font-mono text-[12.5px] leading-relaxed">
                    {step.artifact}
                  </div>
                </li>
              )
            })}
          </ol>
        </div>

        <MeasuredFacts />
      </div>
    </section>
  )
}

/* Measured on our own demo calls (see docs); no projected or customer numbers. */
const FACTS = [
  { value: '~5 s', label: 'from the end of the rep’s sentence to the alert card on screen' },
  { value: '1.0', label: 'text similarity between the spoken alert and the signed clause' },
  { value: '~$0.15', label: 'of API usage for one full demo call' },
]

function MeasuredFacts() {
  return (
    <div className="mt-20 border-t border-border/70 pt-10 md:mt-24">
      <h3 className="text-[15px] font-medium text-text-secondary">Measured on our demo calls</h3>
      <dl className="mt-6 grid grid-cols-1 gap-8 sm:grid-cols-3 sm:gap-8">
        {FACTS.map((f) => (
          // visual order value-then-label; DOM order label-then-value so it reads as a sentence
          <div key={f.value} className="flex flex-col-reverse">
            <dt className="mt-2 max-w-[18rem] text-[15px] leading-relaxed text-text-muted">{f.label}</dt>
            <dd className="font-display text-[28px] font-bold leading-[1.2] tracking-[-0.02em] tabular-nums text-text-primary md:text-[40px] md:leading-[1.15]">
              {f.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Who it's for — gapless bento: what risk it removes, for whom        */
/* 6-col grid, dense flow: [A 4x2][B 2x1][C 2x1] / [D 3x1][E 3x1]      */
/* No stats or logos: every line describes what the product does.      */
/* ------------------------------------------------------------------ */

const EXAMPLES = [
  { said: 'We’ll knock ten percent off if you sign today.', section: '3.1' },
  { said: 'You can cancel mid-term whenever you like.', section: '4.2' },
  { said: 'Deleted data stays recoverable for a full year.', section: '5.3' },
  { said: 'We answer P1 tickets around the clock.', section: '6.1' },
]

function WhoItsFor() {
  return (
    <section aria-labelledby="who-heading" className="px-6 py-32 md:py-44">
      <div className="mx-auto max-w-6xl">
        <h2 id="who-heading" className="max-w-3xl font-display text-[28px] font-bold leading-[1.2] tracking-[-0.02em] text-balance text-text-primary md:text-[40px] md:leading-[1.15]">
          For teams whose contracts can&rsquo;t bend on a sales call
        </h2>

        <div className="mt-14 grid grid-flow-dense grid-cols-1 gap-4 md:grid-cols-6">
          <SpotlightCard className="rounded-2xl p-6 md:col-span-4 md:row-span-2 md:p-8">
            <h3 className="relative max-w-xl font-display text-xl font-semibold leading-[1.3] text-balance text-text-primary md:text-[28px] md:leading-[1.2]">
              A verbal promise gets corrected before it becomes a dispute
            </h3>
            <p className="relative mt-3 max-w-xl text-[15px] leading-relaxed text-text-secondary">
              Discounts, renewal terms, retention, support hours. When a rep says something the signed contract
              doesn&rsquo;t allow, the correction lands while the customer is still listening.
            </p>
            <ul className="relative mt-8">
              {EXAMPLES.map((ex) => (
                <li key={ex.section} className="flex items-center justify-between gap-4 border-t border-border/70 py-3.5">
                  <span className="min-w-0 text-[15px] text-text-primary">&ldquo;{ex.said}&rdquo;</span>
                  <Chip tone="risk-high" mono>
                    §{ex.section}
                  </Chip>
                </li>
              ))}
            </ul>
            <p className="relative mt-2 text-[12px] text-text-muted">Example lines, each contradicting a clause in the demo contract.</p>
          </SpotlightCard>

          <BentoCell icon={<Users size={18} strokeWidth={1.5} />} title="Sales and RevOps leads" className="md:col-span-2">
            See what was promised on every monitored call, next to the section it broke.
          </BentoCell>

          <BentoCell icon={<Quote size={18} strokeWidth={1.5} />} title="Legal and compliance" className="md:col-span-2">
            Every alert quotes the signed clause word for word. No model paraphrases the contract.
          </BentoCell>

          <BentoCell icon={<FileText size={18} strokeWidth={1.5} />} title="A report when the call ends" className="md:col-span-3">
            Each contradiction on a timeline: what the rep said, and the clause it contradicted.
            <MiniTimeline />
          </BentoCell>

          <BentoCell icon={<ShieldCheck size={18} strokeWidth={1.5} />} title="Consent before it listens" className="md:col-span-3">
            A call can&rsquo;t start until a contract is loaded and the rep confirms the call is being monitored.
          </BentoCell>
        </div>
      </div>
    </section>
  )
}

function BentoCell({ icon, title, className, children }: { icon: ReactNode; title: string; className?: string; children: ReactNode }) {
  return (
    <SpotlightCard className={cn('flex flex-col rounded-2xl p-6', className)}>
      <span aria-hidden="true" className="relative grid h-9 w-9 place-items-center rounded-lg border border-border bg-bg-raised text-brand-light">
        {icon}
      </span>
      <h3 className="relative mt-5 font-display text-xl font-semibold leading-[1.3] text-text-primary">{title}</h3>
      <div className="relative mt-2 flex flex-1 flex-col text-[15px] leading-relaxed text-text-muted">{children}</div>
    </SpotlightCard>
  )
}

/** Decorative: dots on a call timeline, like the report screen. */
function MiniTimeline() {
  const marks = [
    { at: '22%', tone: 'bg-risk-high' },
    { at: '58%', tone: 'bg-risk-medium' },
    { at: '84%', tone: 'bg-risk-high' },
  ]
  return (
    <div aria-hidden="true" className="relative mt-auto h-6 pt-6">
      <div className="absolute inset-x-0 top-[33px] h-px bg-border" />
      {marks.map((m) => (
        <span
          key={m.at}
          className={cn('absolute top-[29px] h-2 w-2 -translate-x-1/2 rounded-full ring-4 ring-surface', m.tone)}
          style={{ left: m.at }}
        />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Closing CTA                                                         */
/* ------------------------------------------------------------------ */

function ClosingCta({ onStart }: { onStart: () => void }) {
  return (
    <section aria-labelledby="cta-heading" className="relative overflow-hidden px-6 py-32 text-center md:py-48">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_50%_60%_at_50%_100%,rgba(79,70,229,0.22),transparent_70%)]"
      />
      <div className="relative mx-auto max-w-3xl">
        <h2 id="cta-heading" className="font-display text-[clamp(2.25rem,5vw,4rem)] font-bold leading-[1.05] tracking-[-0.035em] text-balance text-text-primary">
          Try to slip one past it.
        </h2>
        <p className="mx-auto mt-5 max-w-lg text-lg leading-relaxed text-pretty text-text-secondary">
          Load the demo contract, start the call, and offer a discount section 3.1 doesn&rsquo;t allow.
        </p>
        <div className="mt-10 flex justify-center">
          <CtaButton onClick={onStart} size="lg" label="Try the live demo" />
        </div>
      </div>
    </section>
  )
}

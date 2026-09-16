import { useId } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowRight, Check, Loader2, ShieldCheck, TriangleAlert } from 'lucide-react'
import { Button, Card } from '../ui'
import { spring } from '../ui/motion'
import { cn } from '../../lib/cn'

interface ConsentCardProps {
  consent: boolean
  onConsentChange: (accepted: boolean) => void
  starting: boolean
  startError: string | null
  onStart: () => void
  /** seconds — lets the card land after the clause reveal finishes */
  delay?: number
}

/** UI_SCREENS_SPEC.md §3 consent step: its own card, not a checkbox buried
 * in a form. The whole row is the hit target; the checkbox is a custom box
 * over a real (visually hidden) <input type=checkbox>, so keyboard + screen
 * readers get native semantics. A disabled Start never fails silently: the
 * reason is visible text (no hover needed on touch) wired via
 * aria-describedby. */
export default function ConsentCard({ consent, onConsentChange, starting, startError, onStart, delay = 0 }: ConsentCardProps) {
  const hintId = useId()
  const errorId = useId()
  const canStart = consent && !starting

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring.soft, delay }}>
      <Card
        className={cn(
          'space-y-4 px-4 py-4 transition-[border-color,box-shadow] duration-[var(--dur-slow)] sm:px-5 sm:py-5',
          consent ? 'border-safe/35' : 'border-border',
        )}
      >
        <div className="flex items-center gap-2">
          <ShieldCheck size={16} className="text-brand-light" aria-hidden />
          <h3 className="font-display text-[15px] font-semibold text-text-primary">Before we listen</h3>
        </div>

        <label
          className={cn(
            'group flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors duration-[var(--dur-base)]',
            'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-voice-active has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-bg-base',
            consent ? 'border-safe/30 bg-safe/[0.06]' : 'border-border bg-bg-sunken/50 hover:border-border-strong',
          )}
        >
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => onConsentChange(e.target.checked)}
            className="peer sr-only"
          />
          <motion.span
            aria-hidden
            animate={{
              backgroundColor: consent ? 'var(--safe)' : 'rgba(0,0,0,0)',
              borderColor: consent ? 'var(--safe)' : 'var(--border-strong)',
              scale: consent ? [1, 1.12, 1] : 1,
            }}
            transition={{ duration: 0.28 }}
            className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] border-[1.5px] text-bg-base"
          >
            <AnimatePresence>
              {consent && (
                <motion.span initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.4, opacity: 0 }} transition={spring.snappy}>
                  <Check size={14} strokeWidth={3} />
                </motion.span>
              )}
            </AnimatePresence>
          </motion.span>
          <span className="text-[14.5px] leading-snug text-text-primary">
            Everyone on the call has been told it's monitored
            <span className="mt-1 block text-[13px] font-normal text-text-muted">
              Disclosed consent is what keeps a monitored call compliant.
            </span>
          </span>
        </label>

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p id={hintId} className="text-center text-[13px] text-text-muted sm:text-left" aria-live="polite">
            {consent ? (
              <span className="inline-flex items-center gap-1.5 text-safe-text">
                <Check size={14} strokeWidth={2.5} aria-hidden /> Ready when you are
              </span>
            ) : (
              'Confirm disclosure to start the call.'
            )}
          </p>
          <Button
            type="button"
            variant="primary"
            onClick={onStart}
            disabled={!canStart}
            aria-describedby={startError ? `${hintId} ${errorId}` : hintId}
            className="group/start h-11 w-full rounded-full px-5 sm:w-auto"
          >
            {starting ? <Loader2 size={15} className="animate-spin" aria-hidden /> : null}
            {starting ? 'Starting…' : 'Start the call'}
            {!starting && (
              <ArrowRight size={15} className="transition-transform duration-[var(--dur-fast)] group-hover/start:translate-x-0.5" aria-hidden />
            )}
          </Button>
        </div>

        {startError && (
          <p id={errorId} role="alert" className="flex items-start gap-2 rounded-md border border-risk-high/40 bg-risk-high/10 px-3 py-2 text-[13px] text-risk-high-text">
            <TriangleAlert size={15} className="mt-0.5 shrink-0" aria-hidden />
            <span>Couldn't start the call: {startError}</span>
          </p>
        )}
      </Card>
    </motion.div>
  )
}

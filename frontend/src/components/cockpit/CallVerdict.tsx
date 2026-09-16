import { memo } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { cn } from '../../lib/cn'
import { spring } from '../ui/motion'

/** Numeral that pops when it changes (key swap), tabular so width never jumps. */
function Stat({ label, value, tone = 'neutral' }: { label: string; value: string | number; tone?: 'neutral' | 'risk' | 'safe' }) {
  return (
    <div className={cn('min-w-0 px-4 py-2.5', tone === 'neutral' && 'cc-recede')}>
      <p className="truncate text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{label}</p>
      <div className="relative mt-0.5 h-7 overflow-hidden">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={value}
            initial={{ y: 14, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -14, opacity: 0 }}
            transition={spring.snappy}
            className={cn(
              'absolute inset-0 font-display text-[22px] font-bold leading-7 tabular-nums',
              tone === 'risk' ? 'text-risk-high-text' : tone === 'safe' ? 'text-safe-text' : 'text-text-primary',
            )}
          >
            {value}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  )
}

/** Operator overview strip: answers "is this call OK right now?" before the
 * eye reaches any card. Every number is derived from session state, no
 * invented scores. */
export const CallVerdict = memo(function CallVerdict({
  connected,
  checked,
  contradictions,
  spoken,
}: {
  connected: boolean
  checked: number
  contradictions: number
  spoken: number
}) {
  const atRisk = contradictions > 0
  const Icon = atRisk ? ShieldAlert : ShieldCheck

  return (
    <div
      className={cn(
        'mx-5 mt-4 grid shrink-0 grid-cols-[1.4fr_1fr_1fr_1fr] divide-x divide-border/60 overflow-hidden rounded-lg border bg-bg-raised transition-colors duration-500',
        atRisk ? 'border-risk-high/40' : 'border-border',
      )}
    >
      <div className={cn('flex items-center gap-3 px-4 py-2.5 transition-colors duration-500', atRisk ? 'bg-risk-high/10' : 'bg-safe/[0.06]')}>
        <span
          className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-full',
            atRisk ? 'bg-risk-high/20 text-risk-high-text' : 'bg-safe/15 text-safe-text',
          )}
        >
          <Icon size={18} strokeWidth={2} />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Call status</p>
          <p className={cn('truncate font-display text-[16px] font-bold', atRisk ? 'text-risk-high-text' : 'text-safe-text')}>
            {!connected ? 'Connecting' : atRisk ? 'Off-contract' : 'On-contract'}
          </p>
        </div>
      </div>
      <Stat label="Lines checked" value={checked} />
      <Stat label="Contradictions" value={contradictions} tone={atRisk ? 'risk' : 'neutral'} />
      <Stat label="Read verbatim" value={contradictions ? `${spoken}/${contradictions}` : '—'} tone={atRisk && spoken === contradictions ? 'safe' : 'neutral'} />
    </div>
  )
})

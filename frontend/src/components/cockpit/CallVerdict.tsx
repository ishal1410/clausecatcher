import { memo } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { ClaimCheckState } from '../../lib/protocol'
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

/** The headline verdict, and the one claim the whole product rests on.
 *
 * "On-contract" is a statement that every line WAS checked and none
 * contradicted the contract. It may only be said when the server reports the
 * claim-check leg ready AND no check has failed this call — otherwise the
 * honest answer is that we do not know. A contradiction we already found
 * stands on its own evidence, so it still outranks a later check failure. */
export function callStatus(
  connected: boolean,
  contradictions: number,
  claimCheck: ClaimCheckState | undefined,
  checkFailed: boolean,
): { label: string; tone: 'safe' | 'risk' | 'unknown' } {
  if (contradictions > 0) return { label: 'Off-contract', tone: 'risk' }
  if (!connected) return { label: 'Connecting', tone: 'unknown' }
  if (claimCheck !== 'ready' || checkFailed) return { label: 'Not checked', tone: 'unknown' }
  return { label: 'On-contract', tone: 'safe' }
}

/** Operator overview strip: answers "is this call OK right now?" before the
 * eye reaches any card. Every number is derived from session state, no
 * invented scores. */
export const CallVerdict = memo(function CallVerdict({
  connected,
  checked,
  contradictions,
  spoken,
  claimCheck,
  checkFailed = false,
}: {
  connected: boolean
  checked: number
  contradictions: number
  spoken: number
  claimCheck?: ClaimCheckState
  checkFailed?: boolean
}) {
  const atRisk = contradictions > 0
  const status = callStatus(connected, contradictions, claimCheck, checkFailed)
  // Nothing was verified, so a count of "checked" lines would be a second
  // false claim sitting next to the first one.
  const unknown = status.tone === 'unknown' && connected
  const Icon = atRisk ? ShieldAlert : unknown ? ShieldQuestion : ShieldCheck

  return (
    <div
      className={cn(
        'mx-5 mt-4 grid shrink-0 grid-cols-[1.4fr_1fr_1fr_1fr] divide-x divide-border/60 overflow-hidden rounded-lg border bg-bg-raised transition-colors duration-500',
        atRisk ? 'border-risk-high/40' : 'border-border',
      )}
    >
      <div
        className={cn(
          'flex items-center gap-3 px-4 py-2.5 transition-colors duration-500',
          atRisk ? 'bg-risk-high/10' : unknown ? 'bg-risk-medium/[0.08]' : 'bg-safe/[0.06]',
        )}
      >
        <span
          className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-full',
            atRisk ? 'bg-risk-high/20 text-risk-high-text' : unknown ? 'bg-risk-medium/20 text-text-secondary' : 'bg-safe/15 text-safe-text',
          )}
        >
          <Icon size={18} strokeWidth={2} />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Call status</p>
          <p
            className={cn(
              'truncate font-display text-[16px] font-bold',
              atRisk ? 'text-risk-high-text' : unknown ? 'text-text-secondary' : 'text-safe-text',
            )}
            title={unknown ? 'The contradiction check is not running, so these lines were never verified against the contract.' : undefined}
          >
            {status.label}
          </p>
        </div>
      </div>
      <Stat label="Lines checked" value={unknown ? '—' : checked} />
      <Stat label="Contradictions" value={contradictions} tone={atRisk ? 'risk' : 'neutral'} />
      <Stat label="Read verbatim" value={contradictions ? `${spoken}/${contradictions}` : '—'} tone={atRisk && spoken === contradictions ? 'safe' : 'neutral'} />
    </div>
  )
})

import { memo } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { Circle, CircleDot, TriangleAlert } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { AlertRecord } from '../../hooks/useSession'
import type { Clause } from '../../lib/protocol'

type Status = 'watching' | 'referenced' | 'contradicted'

const STATUS: Record<Status, { label: string; Icon: typeof Circle; tile: string; text: string }> = {
  watching: { label: 'Watching', Icon: Circle, tile: 'border-border/70 bg-bg-raised', text: 'text-text-muted' },
  referenced: { label: 'Referenced', Icon: CircleDot, tile: 'border-brand/40 bg-brand/[0.07]', text: 'text-brand-light' },
  contradicted: { label: 'Contradicted', Icon: TriangleAlert, tile: 'border-risk-high/50 bg-risk-high/10', text: 'text-risk-high-text' },
}

/** Clause watchlist: every loaded clause as a tile with icon + text status
 * (never color-only). Sits under the alert stack so the center column reads
 * "verdict -> evidence -> coverage" top to bottom. */
export const ClauseRiskMeter = memo(function ClauseRiskMeter({ clauses, alerts, askedClauses }: { clauses: Clause[]; alerts: AlertRecord[]; askedClauses: Clause[] }) {
  const reducedMotion = useReducedMotion()
  const contradicted = new Set(alerts.map((a) => a.section_number))
  const asked = new Set(askedClauses.map((c) => c.section_number))
  const current = alerts[0]

  return (
    <section aria-label="Clause watchlist" className="shrink-0 border-t border-border/60 bg-bg-base/60 px-5 pb-4 pt-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Clause watchlist</h2>
        <span className="font-mono text-[11px] tabular-nums text-text-muted">
          {clauses.length} monitored{contradicted.size > 0 && <span className="text-risk-high-text"> · {contradicted.size} breached</span>}
        </span>
      </div>

      {clauses.length === 0 ? (
        <p className="text-[13px] text-text-muted">No contract loaded.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-2 sm:max-h-[132px] sm:grid-cols-2 sm:overflow-y-auto">
          {clauses.map((c) => {
            const status: Status = contradicted.has(c.section_number) ? 'contradicted' : asked.has(c.section_number) ? 'referenced' : 'watching'
            const { label, Icon, tile, text } = STATUS[status]
            const pulse = current?.section_number === c.section_number && !reducedMotion
            return (
              <motion.li
                key={c.section_number}
                animate={pulse ? { scale: [1, 1.03, 1] } : undefined}
                transition={pulse ? { duration: 0.5, repeat: 2, delay: 0.3 } : undefined}
                className={cn(
                  'flex min-w-0 items-center gap-2.5 rounded-md border px-3 py-2 transition-colors duration-500',
                  tile,
                  status !== 'contradicted' && 'cc-recede',
                )}
              >
                <Icon size={14} strokeWidth={2} className={cn('shrink-0', text)} />
                <span className="shrink-0 font-mono text-[12px] tabular-nums text-text-secondary">§{c.section_number}</span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-text-primary">{c.title}</span>
                <span className={cn('shrink-0 text-[11px] font-semibold', text)}>{label}</span>
              </motion.li>
            )
          })}
        </ul>
      )}
    </section>
  )
})

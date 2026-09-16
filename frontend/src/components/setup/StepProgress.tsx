import { motion } from 'motion/react'
import { Check } from 'lucide-react'
import { spring, duration, easing } from '../ui/motion'

export type SetupStep = 'contract' | 'consent' | 'live'

const STEPS: { key: SetupStep; label: string }[] = [
  { key: 'contract', label: 'Contract' },
  { key: 'consent', label: 'Consent' },
  { key: 'live', label: 'Go live' },
]

/** DESIGN_SYSTEM.md §5 StepProgress: numbered nodes, connecting line fills
 * brand as steps complete, current step gets an accent ring. */
export default function StepProgress({ current }: { current: SetupStep }) {
  const currentIndex = STEPS.findIndex((s) => s.key === current)

  return (
    <ol aria-label="Setup progress" className="flex items-center gap-2 sm:gap-3">
      {STEPS.map((step, i) => {
        const done = i < currentIndex
        const active = i === currentIndex
        return (
          <li key={step.key} className="flex flex-1 items-center gap-2 sm:gap-3 last:flex-none">
            <div className="flex items-center gap-2" aria-current={active ? 'step' : undefined}>
              <motion.span
                animate={{
                  backgroundColor: done || active ? 'var(--brand)' : 'transparent',
                  borderColor: done || active ? 'var(--brand)' : 'var(--border)',
                  // color-mix, not `var(--brand)33` — hex-alpha suffixes don't apply to var() values
                  boxShadow: active
                    ? '0 0 0 4px color-mix(in oklab, var(--brand) 22%, transparent)'
                    : '0 0 0 0px transparent',
                  color: done || active ? 'var(--text-primary)' : 'var(--text-muted)',
                }}
                transition={spring.snappy}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold"
              >
                {done ? <Check size={13} strokeWidth={2.5} /> : i + 1}
              </motion.span>
              <span className={`text-[13px] font-medium ${active ? 'inline text-text-primary' : 'hidden text-text-muted sm:inline'}`}>
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className="h-px flex-1 overflow-hidden rounded-full bg-border">
                <motion.div
                  className="h-full bg-brand"
                  initial={false}
                  animate={{ width: done ? '100%' : '0%' }}
                  transition={{ duration: duration.slow, ease: easing.standard }}
                />
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}

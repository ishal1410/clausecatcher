/**
 * StatusDot — dot + label (docs/DESIGN_SYSTEM.md §5 "StatusPills"). Dot
 * color is the only color signal, so `label` is required text, never omit
 * it for a bare dot (§7 accessibility: severity is never color-only).
 * The ping ring is decorative and disappears under prefers-reduced-motion.
 */
import { cn } from '../../lib/cn'

export type StatusTone = 'live' | 'connected' | 'neutral' | 'error'

const toneClasses: Record<StatusTone, string> = {
  live: 'bg-voice-active',
  connected: 'bg-safe',
  neutral: 'bg-text-muted',
  error: 'bg-risk-high',
}

export function StatusDot({
  label,
  tone = 'neutral',
  pulse = false,
  className,
}: {
  label: string
  tone?: StatusTone
  pulse?: boolean
  className?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.05em] text-text-secondary', className)}>
      <span className="relative flex h-2 w-2" aria-hidden>
        {pulse && (
          <span className={cn('absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 motion-reduce:hidden', toneClasses[tone])} />
        )}
        <span className={cn('relative inline-flex h-2 w-2 rounded-full shadow-[0_0_0_3px_rgba(255,255,255,0.04)]', toneClasses[tone])} />
      </span>
      {label}
    </span>
  )
}

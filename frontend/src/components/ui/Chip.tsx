/**
 * Chip — pill badge, ui-xs token (docs/DESIGN_SYSTEM.md §3/§5). Covers
 * section-number chips, "StatusPills", and severity badges like
 * "Spoken verbatim". Severity is never color-only: pass `icon`.
 * `mono` chips use mono-meta (12px) — citations like §4.2 need to be read.
 */
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type ChipTone = 'neutral' | 'brand' | 'safe' | 'risk-high' | 'risk-medium' | 'voice'

const toneClasses: Record<ChipTone, string> = {
  neutral: 'bg-surface-glass text-text-secondary border-border',
  brand: 'bg-brand/15 text-brand-light border-brand/30',
  safe: 'bg-safe/12 text-safe-text border-safe/30',
  'risk-high': 'bg-risk-high/12 text-risk-high-text border-risk-high/35',
  'risk-medium': 'bg-risk-medium/12 text-risk-medium-text border-risk-medium/30',
  voice: 'bg-voice-active/12 text-voice-active-text border-voice-active/30',
}

export function Chip({
  children,
  tone = 'neutral',
  icon,
  mono = false,
  className,
}: {
  children: ReactNode
  tone?: ChipTone
  icon?: ReactNode
  mono?: boolean
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase leading-none tracking-[0.05em]',
        '[&_svg]:shrink-0',
        mono && 'font-mono text-[12px] font-medium normal-case tracking-normal tabular-nums',
        toneClasses[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}

/**
 * Card — the base "surface" panel (docs/DESIGN_SYSTEM.md §5). lg radius,
 * hairline border, soft layered shadow with a 1px top inner highlight (the
 * lit-edge that separates a raised panel from the slate base). `glass` opts
 * into backdrop-blur — per DESIGN_SYSTEM.md §1/UI_SCREENS_SPEC §6 that's
 * reserved for chrome (top bars, sheets), never a blanket card treatment,
 * so it defaults off. `glow` adds the severity glow ring from §4.
 */
import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type CardGlow = 'none' | 'risk-high' | 'risk-medium' | 'safe' | 'brand'

const glowVar: Record<Exclude<CardGlow, 'none'>, string> = {
  'risk-high': 'var(--risk-high)',
  'risk-medium': 'var(--risk-medium)',
  safe: 'var(--safe)',
  brand: 'var(--brand)',
}

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  glass?: boolean
  glow?: CardGlow
  accent?: boolean // left 3px accent bar, e.g. ClauseCard
}

export function Card({ glass = false, glow = 'none', accent = false, className, style, children, ...props }: CardProps) {
  const glowColor = glow !== 'none' ? glowVar[glow] : null
  return (
    <div
      className={cn(
        'relative rounded-lg border border-border shadow-card',
        glass ? 'bg-surface-glass backdrop-blur-md' : 'bg-surface',
        accent && 'border-l-[3px] border-l-brand pl-[calc(1rem-3px)]',
        className,
      )}
      style={
        glowColor
          ? {
              // color-mix, not `${var}33` — hex-alpha suffixes don't work on var() values
              boxShadow: `0 0 0 1px color-mix(in oklab, ${glowColor} 20%, transparent), 0 0 24px color-mix(in oklab, ${glowColor} 30%, transparent), var(--shadow-card)`,
              ...style,
            }
          : style
      }
      {...props}
    >
      {children}
    </div>
  )
}

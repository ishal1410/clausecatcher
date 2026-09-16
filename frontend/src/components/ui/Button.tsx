/**
 * Button — docs/DESIGN_SYSTEM.md §5 "Buttons": primary (brand fill),
 * secondary (surface-glass + border), destructive (risk-high fill), plus
 * ghost/outline-destructive used across docs/UI_SCREENS_SPEC.md ("Use demo
 * contract", "Export PDF", "End call").
 *
 * Primary fills with brand-strong (#4F46E5, 6.3:1 with white) rather than
 * brand (#6366F1, 4.47:1 — fails AA for 15px text despite DESIGN_SYSTEM.md
 * listing 5.0). Press feedback is a CSS scale, not motion.button, so the
 * public props stay plain ButtonHTMLAttributes.
 */
import { forwardRef } from 'react'
import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive' | 'outline-destructive'
export type ButtonSize = 'sm' | 'md'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-brand-strong text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.14),0_1px_2px_rgba(0,0,0,0.3),0_8px_20px_-12px_rgba(79,70,229,0.35)] hover:bg-brand-strong-hover',
  secondary:
    'bg-surface-glass text-text-primary border border-border shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] hover:border-border-strong hover:bg-surface',
  ghost: 'bg-transparent text-text-secondary hover:text-text-primary hover:bg-surface',
  destructive: 'bg-risk-high-strong text-white hover:bg-risk-high-strong-hover',
  'outline-destructive': 'bg-transparent text-risk-high-text border border-risk-high/40 hover:bg-risk-high/10',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-9 px-3 text-[13px] gap-1.5',
  md: 'h-10 px-4 text-[15px] gap-2',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', className, children, type = 'button', ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        'inline-flex select-none items-center justify-center whitespace-nowrap rounded-md font-medium',
        'transition-[background-color,border-color,color,filter,transform] duration-[var(--dur-fast)] ease-out',
        'active:scale-[0.98] motion-reduce:active:scale-100',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-voice-active focus-visible:ring-offset-2 focus-visible:ring-offset-bg-base',
        'disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none',
        '[&_svg]:shrink-0',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
})

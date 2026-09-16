/**
 * Toast — bottom-right stack (docs/DESIGN_SYSTEM.md §5 "Toasts"). Kept as a
 * dumb, controlled stack (no context/provider) — the only producers are
 * App.tsx (session/API errors), so a single array of props is enough;
 * add a context if a third screen needs to push toasts independently.
 *
 * Auto-dismisses after 5s; hovering or focusing a toast pauses the timer
 * (restarts in full on leave). Esc dismisses the focused toast. The stack is
 * a polite live region so errors are announced without stealing focus.
 */
import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { AlertTriangle, Info, X } from 'lucide-react'
import { cn } from '../../lib/cn'
import { duration, easing, spring } from './motion'

export interface ToastItem {
  id: string
  message: string
  tone?: 'risk-high' | 'neutral'
}

const AUTO_DISMISS_MS = 5000

const barTone: Record<NonNullable<ToastItem['tone']>, string> = {
  'risk-high': 'border-l-risk-high',
  neutral: 'border-l-border-strong',
}

function Toast({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const [paused, setPaused] = useState(false)
  const tone = toast.tone ?? 'risk-high'

  useEffect(() => {
    if (paused) return
    const timer = window.setTimeout(() => onDismiss(toast.id), AUTO_DISMISS_MS)
    return () => window.clearTimeout(timer)
  }, [paused, toast.id, onDismiss])

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 24, scale: 0.98 }}
      animate={{ opacity: 1, x: 0, scale: 1, transition: spring.snappy }}
      exit={{ opacity: 0, scale: 0.98, transition: { duration: duration.fast, ease: easing.exit } }}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      onKeyDown={(e) => e.key === 'Escape' && onDismiss(toast.id)}
      className={cn(
        'pointer-events-auto flex items-start gap-2.5 rounded-lg border border-border border-l-[3px] bg-surface-glass px-3.5 py-3 text-[13px] leading-snug text-text-primary shadow-card backdrop-blur-md',
        barTone[tone],
      )}
    >
      {tone === 'risk-high' ? (
        <AlertTriangle size={15} className="mt-px text-risk-high-text" aria-hidden />
      ) : (
        <Info size={15} className="mt-px text-text-muted" aria-hidden />
      )}
      <p className="flex-1">
        <span className="sr-only">{tone === 'risk-high' ? 'Error: ' : 'Notice: '}</span>
        {toast.message}
      </p>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="-m-1.5 grid h-7 w-7 shrink-0 place-items-center rounded-md text-text-muted transition-colors hover:bg-surface hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-voice-active"
      >
        <X size={14} aria-hidden />
      </button>
    </motion.div>
  )
}

export function ToastStack({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  return (
    <div
      role="region"
      aria-label="Notifications"
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 left-4 z-50 ml-auto flex max-w-sm flex-col gap-2 print:hidden"
    >
      <AnimatePresence initial={false} mode="sync">
        {toasts.map((t) => (
          <Toast key={t.id} toast={t} onDismiss={onDismiss} />
        ))}
      </AnimatePresence>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { CircleAlert, X } from 'lucide-react'

export function ErrorToast({ message }: { message: string | null }) {
  const reducedMotion = useReducedMotion()
  const [dismissed, setDismissed] = useState<string | null>(null)

  useEffect(() => {
    if (!message) return
    setDismissed(null)
    const id = window.setTimeout(() => setDismissed(message), 5000)
    return () => window.clearTimeout(id)
  }, [message])

  const visible = message && message !== dismissed

  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-50" style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}>
      <AnimatePresence>
        {visible && (
          <motion.div
            initial={reducedMotion ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            role="alert"
            className="pointer-events-auto flex max-w-sm items-start gap-2.5 rounded-lg border border-risk-high/30 bg-surface p-3.5 shadow-[0_4px_24px_rgba(0,0,0,.35)]"
          >
            <CircleAlert size={16} strokeWidth={1.75} className="mt-0.5 shrink-0 text-risk-high-text" />
            <p className="text-[13px] leading-snug text-text-primary">{message}</p>
            <button onClick={() => setDismissed(message)} aria-label="Dismiss" className="ml-auto shrink-0 text-text-muted hover:text-text-primary">
              <X size={14} strokeWidth={1.75} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

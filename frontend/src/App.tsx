/**
 * App.tsx — state machine: landing -> setup -> cockpit -> report, per
 * docs/UI_SCREENS_SPEC.md §1 IA. One useSession() instance lives here and
 * is threaded into Cockpit; ending the call stops the session and swaps to
 * the report screen (report data arrives via the WS session_ended message,
 * falling back to the REST endSession call after 1.5s, mirroring the
 * fetchReportFallback behavior in web/app.js).
 *
 * Landing/Setup/Cockpit are owned by other agents building them in
 * parallel (components/landing, components/setup, components/cockpit).
 * They're loaded via import.meta.glob rather than a static import so this
 * file — and `tsc`/`vite build` — keep working before those files land;
 * once a real file exists, the glob picks it up automatically, no edit
 * needed here.
 */
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import type { ComponentType } from 'react'
import { AnimatePresence, MotionConfig, motion } from 'motion/react'
import * as api from './lib/api'
import { useSession } from './hooks/useSession'
import type { Clause } from './lib/protocol'
import { Card, StatusDot, ToastStack, pageTransition } from './components/ui'
import type { ToastItem } from './components/ui'
import { Report } from './components/report/Report'

type Page = 'landing' | 'setup' | 'cockpit' | 'report'

// -- guarded loaders for sibling-team screens ------------------------------

interface LandingProps {
  onStart: () => void
}
interface SetupProps {
  onReady: (sessionId: string, clauses: Clause[]) => void
}
interface CockpitProps {
  session: ReturnType<typeof useSession>
  clauses: Clause[]
  onEnd: () => void
}

const landingGlob = import.meta.glob<{ default: ComponentType<LandingProps> }>('./components/landing/Landing.tsx')
const setupGlob = import.meta.glob<{ default: ComponentType<SetupProps> }>('./components/setup/Setup.tsx')
const cockpitGlob = import.meta.glob<{ default: ComponentType<CockpitProps> }>('./components/cockpit/Cockpit.tsx')

function placeholder(name: string): ComponentType<Record<string, unknown>> {
  return function BuildingPlaceholder() {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 py-32 text-center">
        <Card className="w-full p-6">
          <StatusDot label={`${name} is still being built`} tone="neutral" pulse />
          <p className="mt-2 text-[13px] text-text-muted">This screen will appear automatically once its file lands.</p>
        </Card>
      </div>
    )
  }
}

function guardedLazy<P extends object>(
  glob: Record<string, () => Promise<{ default: ComponentType<P> }>>,
  name: string,
): ComponentType<P> {
  const entry = Object.values(glob)[0]
  if (!entry) return placeholder(name) as ComponentType<P>
  return lazy(entry)
}

const Landing = guardedLazy<LandingProps>(landingGlob, 'Landing')
const Setup = guardedLazy<SetupProps>(setupGlob, 'Setup')
const Cockpit = guardedLazy<CockpitProps>(cockpitGlob, 'Cockpit')

// -- app ---------------------------------------------------------------

export default function App() {
  const [page, setPage] = useState<Page>('landing')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [clauses, setClauses] = useState<Clause[]>([])
  const [fallbackReport, setFallbackReport] = useState<Awaited<ReturnType<typeof api.endSession>> | null>(null)
  const [reportError, setReportError] = useState<string | null>(null)
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const session = useSession()
  const reportRef = useRef(session.state.report)
  useEffect(() => {
    reportRef.current = session.state.report
  }, [session.state.report])

  const pushToast = useCallback((message: string) => {
    setToasts((prev) => [...prev, { id: crypto.randomUUID(), message }])
  }, [])
  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // surface WS/session errors as toasts without blocking the current screen
  useEffect(() => {
    if (session.state.error) pushToast(session.state.error)
  }, [session.state.error, pushToast])

  const handleReady = useCallback(
    (id: string, loadedClauses: Clause[]) => {
      setSessionId(id)
      setClauses(loadedClauses)
      session.start(id)
      setPage('cockpit')
    },
    [session],
  )

  const attemptReportFallback = useCallback(() => {
    if (!sessionId) return
    setReportError(null)
    api
      .endSession(sessionId)
      .then((r) => setFallbackReport(r))
      .catch((err) => {
        const message = err instanceof Error ? err.message : String(err)
        setReportError(message)
        pushToast(`Could not fetch call report: ${message}`)
      })
  }, [sessionId, pushToast])

  const handleEnd = useCallback(() => {
    session.stop()
    setFallbackReport(null)
    setReportError(null)
    setPage('report')
    // fetchReportFallback equivalent: give session_ended 1.5s before REST fallback
    window.setTimeout(() => {
      if (!reportRef.current) attemptReportFallback()
    }, 1500)
  }, [session, attemptReportFallback])

  const handleNewSession = useCallback(() => {
    setSessionId(null)
    setFallbackReport(null)
    setReportError(null)
    setPage('setup')
  }, [])

  const report = session.state.report ?? fallbackReport

  // a11y: after a step swap, send scroll + focus to the new screen so keyboard
  // and screen-reader users start at its top instead of on a now-gone button.
  // onExitComplete never fires on first mount, so landing keeps default focus.
  const screenRef = useRef<HTMLDivElement>(null)
  const handlePageSwapped = useCallback(() => {
    window.scrollTo({ top: 0 })
    screenRef.current?.focus({ preventScroll: true })
  }, [])

  return (
    // reducedMotion="user": Motion drops transform/layout animation (keeps opacity) for OS reduced-motion users
    <MotionConfig reducedMotion="user">
      <div className="min-h-dvh bg-bg-base text-text-primary">
        {/* plain div, not <main>: Landing renders its own <main> */}
        <div ref={screenRef} tabIndex={-1} className="outline-none">
          <AnimatePresence mode="wait" onExitComplete={handlePageSwapped}>
            {page === 'landing' && (
              <motion.div key="landing" {...pageTransition}>
                <Suspense fallback={null}>
                  <Landing onStart={() => setPage('setup')} />
                </Suspense>
              </motion.div>
            )}
            {page === 'setup' && (
              <motion.div key="setup" {...pageTransition}>
                <Suspense fallback={null}>
                  <Setup onReady={handleReady} />
                </Suspense>
              </motion.div>
            )}
            {page === 'cockpit' && (
              <motion.div key="cockpit" {...pageTransition}>
                <Suspense fallback={null}>
                  <Cockpit session={session} clauses={clauses} onEnd={handleEnd} />
                </Suspense>
              </motion.div>
            )}
            {page === 'report' && (
              <motion.div key="report" {...pageTransition}>
                <Report report={report} error={reportError} onRetry={attemptReportFallback} onNewSession={handleNewSession} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <ToastStack toasts={toasts} onDismiss={dismissToast} />
      </div>
    </MotionConfig>
  )
}

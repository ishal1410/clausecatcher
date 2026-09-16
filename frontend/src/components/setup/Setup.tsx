import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import * as api from '../../lib/api'
import type { Clause } from '../../lib/protocol'
import { duration, easing } from '../ui/motion'
import StepProgress, { type SetupStep } from './StepProgress'
import DropZone, { type UploadStatus } from './DropZone'
import ClauseList from './ClauseList'
import ConsentCard from './ConsentCard'

interface SetupProps {
  onReady: (sessionId: string, clauses: Clause[]) => void
}

const COPY: Record<'empty' | 'loaded', { title: string; sub: string }> = {
  empty: {
    title: 'Load your contract',
    sub: 'Drop the signed PDF. Every clause comes back quoted exactly as written.',
  },
  loaded: {
    title: 'Your contract, clause by clause',
    sub: 'These are the exact words every sentence on the call gets checked against.',
  },
}

function describeError(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** Setup.tsx — UI_SCREENS_SPEC.md §3 "Contract setup". Orchestrates the
 * three-step flow (contract -> consent -> go live) over api.ts; each step's
 * presentation lives in its own file in this folder. */
export default function Setup({ onReady }: SetupProps) {
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [clauses, setClauses] = useState<Clause[]>([])
  const [fileName, setFileName] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [consent, setConsent] = useState(false)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  const loaded = clauses.length > 0
  const step: SetupStep = !loaded ? 'contract' : !consent ? 'consent' : 'live'
  const copy = COPY[loaded ? 'loaded' : 'empty']

  // One path for upload + demo. A failed load keeps whatever contract was
  // already loaded, so "Replace" with a bad file never wipes good clauses.
  async function load(read: () => Promise<Clause[]>, name: string) {
    setStatus('uploading')
    setErrorMsg(null)
    try {
      setClauses(await read())
      setFileName(name)
      setStatus('idle')
    } catch (err) {
      setStatus('error')
      setErrorMsg(describeError(err))
    }
  }

  async function handleStart() {
    setStarting(true)
    setStartError(null)
    try {
      await api.setConsent(true)
      onReady(await api.startSession(), clauses)
    } catch (err) {
      setStarting(false)
      setStartError(describeError(err))
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-8 px-4 py-12 sm:px-6 sm:py-16">
      <StepProgress current={step} />

      <AnimatePresence mode="wait" initial={false}>
        <motion.header
          key={loaded ? 'loaded' : 'empty'}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0, transition: { duration: duration.base, ease: easing.enter } }}
          exit={{ opacity: 0, y: -4, transition: { duration: duration.fast, ease: easing.exit } }}
          className="space-y-2"
        >
          <h1 className="font-display text-[26px] font-bold leading-tight tracking-tight text-balance text-text-primary sm:text-[28px]">
            {copy.title}
          </h1>
          <p className="text-[15px] leading-relaxed text-pretty text-text-muted">{copy.sub}</p>
        </motion.header>
      </AnimatePresence>

      <DropZone
        status={status}
        fileName={loaded ? fileName : null}
        clauseCount={clauses.length}
        errorMsg={errorMsg}
        onFile={(file) => load(() => api.uploadContract(file), file.name)}
        onValidationError={(message) => {
          setStatus('error')
          setErrorMsg(message)
        }}
        onUseDemo={() => load(api.loadDemoContract, 'demo-contract.pdf')}
        onDismissError={() => {
          setErrorMsg(null)
          setStatus('idle')
        }}
      />

      <ClauseList clauses={clauses} />

      {loaded && (
        <ConsentCard
          consent={consent}
          onConsentChange={setConsent}
          starting={starting}
          startError={startError}
          onStart={handleStart}
          delay={Math.min(clauses.length, 8) * 0.09 + 0.3}
        />
      )}
    </div>
  )
}

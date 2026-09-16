import { useRef, useState, type DragEvent, type ReactNode } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { CircleCheck, FileText, FileWarning, RefreshCw, Upload, X } from 'lucide-react'
import { Button } from '../ui'
import { spring } from '../ui/motion'
import { cn } from '../../lib/cn'
import { contractFileProblem } from './contractFile'

export type UploadStatus = 'idle' | 'uploading' | 'error'

interface DropZoneProps {
  status: UploadStatus
  /** set only once a contract is loaded — switches the zone to its compact row */
  fileName: string | null
  clauseCount: number
  errorMsg: string | null
  onFile: (file: File) => void
  onValidationError: (message: string) => void
  onUseDemo: () => void
  onDismissError: () => void
}

const FOCUS_RING =
  'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-voice-active has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-bg-base'

/** DESIGN_SYSTEM.md §5 DropZone + UI_SCREENS_SPEC.md §3: dashed accent
 * border, drag-over glow, skeleton loading, inline server-error text; on
 * success the zone collapses to a compact file row with a Replace action.
 * Both the zone and Replace are a <label> around a visually-hidden file input,
 * so click, tap and keyboard (Tab -> Space/Enter) open the native picker for
 * free — no click-forwarding or focus management needed. */
export default function DropZone({
  status,
  fileName,
  clauseCount,
  errorMsg,
  onFile,
  onValidationError,
  onUseDemo,
  onDismissError,
}: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const dragDepth = useRef(0)
  const reduceMotion = useReducedMotion()
  const loaded = fileName !== null && clauseCount > 0
  const uploading = status === 'uploading'

  function validateAndEmit(file: File) {
    const problem = contractFileProblem(file)
    if (problem) onValidationError(problem)
    else onFile(file)
  }

  const dragHandlers = {
    onDragEnter(e: DragEvent) {
      e.preventDefault()
      dragDepth.current += 1
      setIsDragging(true)
    },
    onDragOver(e: DragEvent) {
      e.preventDefault()
    },
    onDragLeave(e: DragEvent) {
      e.preventDefault()
      dragDepth.current = Math.max(0, dragDepth.current - 1)
      if (dragDepth.current === 0) setIsDragging(false)
    },
    onDrop(e: DragEvent) {
      e.preventDefault()
      dragDepth.current = 0
      setIsDragging(false)
      const file = e.dataTransfer?.files?.[0]
      if (file) validateAndEmit(file)
    },
  }

  const fileInput = (label: string) => (
    <input
      type="file"
      accept="application/pdf,.pdf"
      className="sr-only"
      aria-label={label}
      disabled={uploading}
      onChange={(e) => {
        const file = e.target.files?.[0]
        if (file) validateAndEmit(file)
        e.target.value = ''
      }}
    />
  )

  const dragGlow = {
    boxShadow:
      '0 0 0 1px color-mix(in oklab, var(--brand) 35%, transparent), 0 12px 40px -12px color-mix(in oklab, var(--brand) 45%, transparent)',
  }

  return (
    <div className="space-y-3">
      {/* ponytail: no exit animation on the zone -> row swap. An exiting 240px
          zone holds its height while the clause cards below start revealing,
          then the whole list jumps up ~230px mid-demo. Instant swap = no jump. */}
      {loaded ? (
        <motion.div
          key="loaded"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={spring.soft}
          {...dragHandlers}
          data-testid="drop-zone"
          className={cn(
            'flex items-center gap-3 rounded-lg border bg-surface px-3 py-3 shadow-card transition-colors duration-[var(--dur-base)] sm:px-4',
            isDragging ? 'border-brand' : status === 'error' ? 'border-risk-high/60' : 'border-border',
          )}
          style={isDragging ? dragGlow : undefined}
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-brand/25 bg-brand/12 text-brand-light">
            <FileText size={18} strokeWidth={1.75} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[14px] font-medium text-text-primary" title={fileName ?? undefined}>
              {uploading ? 'Reading new contract…' : fileName}
            </p>
            <p className="mt-0.5 flex items-center gap-1.5 text-[12.5px] text-text-muted">
              <CircleCheck size={13} className="shrink-0 text-safe-text" aria-hidden />
              <span className="tabular-nums">
                {clauseCount} clause{clauseCount === 1 ? '' : 's'}
              </span>
              <span aria-hidden>·</span>
              <span>read verbatim</span>
            </p>
          </div>
          <label
            className={cn(
              'inline-flex h-11 shrink-0 cursor-pointer select-none items-center gap-1.5 rounded-full border border-border bg-surface-glass px-3.5 text-[13px] font-medium text-text-primary transition-colors duration-[var(--dur-fast)] hover:border-border-strong hover:bg-bg-raised sm:h-9',
              FOCUS_RING,
              uploading && 'pointer-events-none opacity-50',
            )}
          >
            {fileInput('Replace contract PDF')}
            <RefreshCw size={14} className={cn(uploading && 'animate-spin')} aria-hidden />
            Replace
          </label>
        </motion.div>
      ) : (
        <motion.div
          key="zone"
          initial={{ opacity: 0 }}
          animate={status === 'error' && !reduceMotion ? { opacity: 1, x: [0, -7, 6, -4, 3, 0] } : { opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
        >
          <label
            {...dragHandlers}
            data-testid="drop-zone"
            className={cn(
              'group relative flex min-h-[240px] cursor-pointer flex-col items-center justify-center gap-3 overflow-hidden rounded-lg border-2 border-dashed px-6 text-center shadow-card backdrop-blur-md transition-[border-color,background-color] duration-[var(--dur-base)]',
              FOCUS_RING,
              status === 'error'
                ? 'border-risk-high/70 bg-risk-high/[0.04]'
                : isDragging
                  ? 'border-brand bg-brand/10'
                  : 'border-border-strong/60 bg-surface-glass hover:border-brand/50',
              uploading && 'pointer-events-none',
            )}
            style={isDragging ? dragGlow : undefined}
          >
            {fileInput('Upload contract PDF')}
            <AnimatePresence mode="wait">
              {uploading ? <ReadingSkeleton key="skeleton" /> : <EmptyPrompt key="empty" isDragging={isDragging} error={status === 'error'} />}
            </AnimatePresence>
          </label>
        </motion.div>
      )}

      <AnimatePresence>
        {status === 'error' && errorMsg && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            role="alert"
            className="flex items-start gap-2.5 rounded-md border border-risk-high/40 bg-risk-high/10 py-2 pl-3 pr-1.5 text-[13.5px] leading-snug text-risk-high-text"
          >
            <FileWarning size={16} className="mt-0.5 shrink-0" aria-hidden />
            <span className="flex-1 py-px">{errorMsg}</span>
            <button
              type="button"
              onClick={onDismissError}
              aria-label="Dismiss error"
              className="-my-1 flex h-8 w-8 shrink-0 items-center justify-center rounded text-risk-high-text hover:bg-risk-high/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-risk-high"
            >
              <X size={15} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {!loaded && (
        <div className="flex items-center gap-3 text-[12px] font-medium uppercase tracking-[0.08em] text-text-muted">
          <span className="h-px flex-1 bg-border" aria-hidden />
          <span>or</span>
          <span className="h-px flex-1 bg-border" aria-hidden />
        </div>
      )}
      {!loaded && (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={onUseDemo}
            disabled={uploading}
            className="h-11 rounded-full px-5 sm:h-10"
          >
            <FileText size={14} aria-hidden />
            Use the demo contract
          </Button>
        </div>
      )}
    </div>
  )
}

function EmptyPrompt({ isDragging, error }: { isDragging: boolean; error: boolean }): ReactNode {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-2.5">
      <motion.div
        animate={{ y: isDragging ? -4 : 0, scale: isDragging ? 1.08 : 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
        className={cn(
          'mx-auto flex h-12 w-12 items-center justify-center rounded-full border transition-colors duration-[var(--dur-base)]',
          error
            ? 'border-risk-high/30 bg-risk-high/10 text-risk-high-text'
            : 'border-brand/25 bg-brand/10 text-brand-light group-hover:border-brand/45',
        )}
      >
        {error ? <FileWarning size={20} strokeWidth={1.75} /> : <Upload size={20} strokeWidth={1.75} />}
      </motion.div>
      <p className="text-[16px] font-medium text-text-primary">
        {isDragging ? (
          'Release to read the contract'
        ) : (
          <>
            <span className="pointer-coarse:hidden">Drop your contract PDF here</span>
            <span className="hidden pointer-coarse:inline">Tap to choose your contract PDF</span>
          </>
        )}
      </p>
      <p className="text-[13px] text-text-muted">
        or <span className="text-brand-light underline decoration-brand-light/40 underline-offset-4">browse files</span> · PDF up to 5 MB
      </p>
    </motion.div>
  )
}

/** Loading state shaped like the clause cards it's about to become (spec §3). */
function ReadingSkeleton(): ReactNode {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="w-full max-w-sm space-y-2.5 text-left"
      aria-busy="true"
      role="status"
      aria-label="Reading contract"
    >
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-3 rounded-md border border-border/70 bg-bg-sunken/60 px-3 py-2.5">
          <div className="h-5 w-10 shrink-0 animate-pulse rounded-full bg-border" style={{ animationDelay: `${i * 120}ms` }} />
          <div className="h-2.5 animate-pulse rounded-full bg-border" style={{ width: `${88 - i * 20}%`, animationDelay: `${i * 120}ms` }} />
        </div>
      ))}
      <p className="pt-1 text-center text-[13px] text-text-muted">Reading contract…</p>
    </motion.div>
  )
}

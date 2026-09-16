import { memo, useEffect, useRef } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Radio } from 'lucide-react'
import { cn } from '../../lib/cn'
import { spring } from '../ui/motion'
import type { AlertRecord, TranscriptLine } from '../../hooks/useSession'

/** Underlines the exact offending `sentence` inside the transcript line.
 * `isNewest` replays the sweep (keyed on the alert timestamp, so unrelated
 * re-renders don't retrigger it); older matches show a settled underline. */
function Line({ line, matchedAlert, isNewest }: { line: TranscriptLine; matchedAlert?: AlertRecord; isNewest: boolean }) {
  const idx = matchedAlert ? line.text.indexOf(matchedAlert.sentence) : -1
  if (!matchedAlert || idx === -1) return <>{line.text}</>
  const end = idx + matchedAlert.sentence.length
  return (
    <>
      {line.text.slice(0, idx)}
      <mark
        key={isNewest ? matchedAlert.t : 'settled'}
        className={cn('rounded-[2px] bg-transparent text-risk-high-text', isNewest && 'cc-anim-sweep')}
        style={{
          backgroundImage: 'linear-gradient(var(--risk-high), var(--risk-high))',
          backgroundRepeat: 'no-repeat',
          backgroundPosition: '0 100%',
          backgroundSize: isNewest ? undefined : '100% 2px',
        }}
      >
        {line.text.slice(idx, end)}
      </mark>
      {line.text.slice(end)}
    </>
  )
}

export const TranscriptPane = memo(function TranscriptPane({ transcript, alerts }: { transcript: TranscriptLine[]; alerts: AlertRecord[] }) {
  const reducedMotion = useReducedMotion()
  const scrollRef = useRef<HTMLDivElement>(null)
  const lastText = transcript[transcript.length - 1]?.text

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [transcript.length, lastText])

  return (
    <section className="flex h-full min-w-0 flex-col border-r border-border/60 bg-bg-base">
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-border/60 px-4">
        <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
          <Radio size={13} strokeWidth={1.75} />
          Live transcript
        </span>
        <span className="font-mono text-[11px] tabular-nums text-text-muted">{transcript.length} lines</span>
      </div>

      {transcript.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <Radio size={22} strokeWidth={1.5} className="text-border-strong" />
          <p className="text-[13px] text-text-muted">Listening for the call to begin.</p>
        </div>
      ) : (
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
          <ol className="relative space-y-3 border-l border-border/70 pl-4">
            <AnimatePresence initial={false}>
              {transcript.map((line, i) => {
                const matched = line.final ? alerts.find((a) => line.text.includes(a.sentence)) : undefined
                const isNewest = !!matched && matched === alerts[0] && !reducedMotion
                return (
                  <motion.li
                    key={i}
                    initial={reducedMotion ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={line.final ? spring.soft : { duration: 0.15 }}
                    className={cn(
                      'relative text-[14px] leading-relaxed',
                      line.final ? 'text-text-primary' : 'italic text-text-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'absolute -left-[21px] top-[9px] h-2 w-2 rounded-full border-2 border-bg-base',
                        matched ? 'bg-risk-high' : line.final ? 'bg-border-strong' : 'bg-voice-active cc-anim-livepulse',
                      )}
                      aria-hidden
                    />
                    {/* recede lives on an inner span: motion's inline opacity on the li would override it */}
                    <span className={cn(!matched && 'cc-recede')}>
                      <Line line={line} matchedAlert={matched} isNewest={isNewest} />
                      {!line.final && (
                        <span className={cn('ml-0.5 inline-block', !reducedMotion && 'cc-anim-ellipsis')} aria-hidden>
                          &hellip;
                        </span>
                      )}
                    </span>
                  </motion.li>
                )
              })}
            </AnimatePresence>
          </ol>
        </div>
      )}
    </section>
  )
})

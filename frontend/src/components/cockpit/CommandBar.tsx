import { memo, useEffect, useRef, useState } from 'react'
import { ChevronDown, Search, Send, Volume2, VolumeX } from 'lucide-react'
import type { Clause } from '../../lib/protocol'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

/** Rail controls. Ask: picking a section sends `ask` immediately (no second
 * click), Cmd/Ctrl+K focuses it. Simulate: a visibly separate, labeled demo
 * aid. The wave-1 "mic display" toggle was removed: useSession has no mute
 * API, so it was a control that did nothing. */
export const CommandBar = memo(function CommandBar({
  clauses,
  answered = [],
  voiceReady = false,
  onAsk,
  onSimulate,
}: {
  clauses: Clause[]
  /** Clauses the server has answered (`clause` frames), oldest first. */
  answered?: Clause[]
  voiceReady?: boolean
  onAsk: (section: string) => void
  onSimulate: (text: string) => void
}) {
  const answer = answered[answered.length - 1]
  const [simulateText, setSimulateText] = useState('')
  const selectRef = useRef<HTMLSelectElement>(null)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        selectRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function handleSimulate() {
    if (!simulateText.trim()) return
    onSimulate(simulateText)
    setSimulateText('')
  }

  return (
    <div className="cc-recede space-y-3">
      <div className="rounded-lg border border-text-primary/8 bg-surface/60 p-3">
        <label htmlFor="cc-ask" className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
          <Search size={12} strokeWidth={1.75} /> Ask a clause aloud
        </label>
        <div className="relative flex items-center rounded-md border border-border bg-bg-sunken focus-within:border-voice-active">
          <select
            id="cc-ask"
            ref={selectRef}
            value=""
            disabled={clauses.length === 0}
            onChange={(e) => e.target.value && onAsk(e.target.value)}
            className="h-10 min-w-0 flex-1 appearance-none bg-transparent pl-3 pr-20 text-[13px] text-text-primary outline-none disabled:text-text-muted"
          >
            <option value="" disabled>
              Pick a section to read&hellip;
            </option>
            {clauses.map((c) => (
              <option key={c.section_number} value={c.section_number} className="bg-surface">
                §{c.section_number} · {c.title}
              </option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-2 flex items-center gap-1.5">
            <kbd className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-text-muted">{isMac ? '⌘' : 'Ctrl'} K</kbd>
            <ChevronDown size={14} strokeWidth={1.75} className="text-text-muted" />
          </span>
        </div>

        {/* The answer, in text. The voice agent reads the same words when a
            voice key is present; without one the clause still has to land
            somewhere, or the control looks inert. Literal contract text only. */}
        {answer && (
          <figure aria-live="polite" className="mt-3 rounded-md border border-brand/30 bg-brand/[0.07] p-2.5">
            <figcaption className="mb-1.5 flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-[12px] font-semibold text-brand-light">
                <span className="font-mono tabular-nums">§{answer.section_number}</span> {answer.title}
              </span>
              <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-text-muted">
                {voiceReady ? <Volume2 size={11} strokeWidth={2} aria-hidden /> : <VolumeX size={11} strokeWidth={2} aria-hidden />}
                {voiceReady ? 'Read aloud' : 'Text only'}
              </span>
            </figcaption>
            <blockquote className="max-h-32 overflow-y-auto font-mono text-[12px] leading-relaxed text-text-primary">
              {answer.literal_text}
            </blockquote>
          </figure>
        )}
      </div>

      <div className="rounded-lg border border-dashed border-border bg-transparent p-3">
        <label htmlFor="cc-sim" className="mb-0.5 block text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
          Simulate rep line
        </label>
        <p className="mb-2 text-[11px] text-text-muted">Demo aid: sent as if the rep said it.</p>
        <div className="flex items-center gap-2">
          <input
            id="cc-sim"
            value={simulateText}
            onChange={(e) => setSimulateText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSimulate()}
            placeholder="We can do a verbal discount…"
            className="h-10 min-w-0 flex-1 rounded-md border border-border bg-bg-sunken px-3 text-[13px] text-text-primary outline-none placeholder:text-border-strong focus:border-voice-active"
          />
          <button
            onClick={handleSimulate}
            disabled={!simulateText.trim()}
            aria-label="Send simulated line"
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-brand-strong text-text-primary transition-[background-color,transform] hover:bg-brand-strong-hover active:scale-[0.96] disabled:opacity-40"
          >
            <Send size={15} strokeWidth={1.75} />
          </button>
        </div>
      </div>
    </div>
  )
})

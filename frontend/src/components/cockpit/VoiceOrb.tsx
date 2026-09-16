import { createContext, memo, use, useLayoutEffect, useRef, type CSSProperties } from 'react'
import { useReducedMotion } from 'motion/react'
import { AudioLines } from 'lucide-react'
import { cn } from '../../lib/cn'

/** Current audio level (0-1), provided by Cockpit's shell at audio-chunk rate. */
export const LevelContext = createContext(0)

const BAR_COUNT = 32
const RADIUS = 62
// Fixed per-bar gain so the ring reads as a waveform, not a uniform halo.
const K = [0.55, 0.9, 0.7, 1, 0.62, 0.84, 0.95, 0.58]

type Mode = 'speaking' | 'listening' | 'idle'

const MODE_VARS: Record<Mode, CSSProperties> = {
  speaking: { color: 'var(--voice-active)', '--cc-base': 0.5, '--cc-gain': 2.4, '--cc-pulse': 0.08 } as CSSProperties,
  listening: { color: 'var(--brand-light)', '--cc-base': 0.4, '--cc-gain': 3.2, '--cc-pulse': 0 } as CSSProperties,
  idle: { color: 'var(--border-strong)', '--cc-base': 0.3, '--cc-gain': 0, '--cc-pulse': 0 } as CSSProperties,
}

/** Static ring markup: memoized so a level change never re-renders 32 bars. */
const Ring = memo(function Ring({ animate }: { animate: boolean }) {
  return (
    <>
      {Array.from({ length: BAR_COUNT }, (_, i) => (
        <span
          key={i}
          className="absolute left-1/2 top-1/2 h-0 w-0"
          style={{ transform: `rotate(${(360 / BAR_COUNT) * i}deg) translateY(-${RADIUS}px)` }}
        >
          <span className="cc-orb-bar" style={{ '--cc-k': K[i % K.length] } as CSSProperties}>
            <span
              className={cn('block h-full w-full rounded-full bg-current', animate && 'cc-anim-wobble')}
              style={{ animationDelay: `${(i % 7) * 0.09}s` }}
            />
          </span>
        </span>
      ))}
    </>
  )
})

/** Kokonut AI Voice style bar ring (see THIRD_PARTY.md). The only cockpit
 * component that reads the audio-rate level (LevelContext); it writes it into
 * a CSS variable imperatively so React never diffs the bars per chunk. */
export function VoiceOrb({ speaking, listening, connected }: { speaking: boolean; listening: boolean; connected: boolean }) {
  const level = use(LevelContext)
  const reducedMotion = useReducedMotion()
  const discRef = useRef<HTMLDivElement>(null)
  const mode: Mode = speaking ? 'speaking' : listening ? 'listening' : 'idle'

  useLayoutEffect(() => {
    discRef.current?.style.setProperty('--cc-level', reducedMotion ? '0' : String(Math.min(1, level)))
  }, [level, reducedMotion])

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        ref={discRef}
        style={MODE_VARS[mode]}
        className={cn(
          'cc-orb relative flex h-40 w-40 items-center justify-center rounded-full border bg-bg-sunken transition-[border-color,box-shadow] duration-500',
          speaking ? 'border-voice-active/40 shadow-[0_0_0_1px_color-mix(in_oklab,var(--voice-active)_25%,transparent),0_0_48px_color-mix(in_oklab,var(--voice-active)_28%,transparent)]' : 'border-border',
          !speaking && !reducedMotion && 'cc-anim-breathe',
        )}
      >
        <span className="absolute inset-5 rounded-full border border-text-primary/5" aria-hidden />
        <Ring animate={!reducedMotion} />
        <AudioLines size={24} strokeWidth={1.75} />
      </div>
      <div className="text-center" aria-live="polite">
        <p className={cn('text-[13px] font-semibold', speaking ? 'text-voice-active-text' : 'text-text-secondary')}>
          {!connected ? 'Connecting…' : speaking ? 'Speaking to the call' : listening ? 'Listening' : 'Idle'}
        </p>
        <p className="mt-0.5 font-mono text-[11px] text-text-muted">AssemblyAI Voice Agent</p>
      </div>
    </div>
  )
}

import { cn } from '../../lib/cn'

export type PillState = 'connecting' | 'connected' | 'active' | 'error' | 'disabled' | 'unavailable'

const DOT: Record<PillState, string> = {
  connecting: 'bg-text-muted',
  connected: 'bg-safe',
  active: 'bg-voice-active cc-anim-livepulse',
  error: 'bg-risk-high',
  disabled: 'bg-border-strong',
  unavailable: 'bg-risk-medium',
}

const LABEL_TEXT: Record<PillState, string> = {
  connecting: 'connecting',
  connected: 'ready',
  active: 'working',
  error: 'error',
  disabled: 'off',
  unavailable: 'not checking',
}

/**
 * The Gemini claim-check leg, straight off the wire (`status.claim_check`).
 * Green ONLY for "ready": this pill used to be hard-wired green whenever the
 * socket was open, so a keyless server looked healthy while it checked
 * nothing (DEMO_DAY_BUGS.md finding 1).
 */
export function claimPillState(raw: string | undefined, connected: boolean, active: boolean): PillState {
  if (raw === 'error') return 'error'
  if (raw === 'disabled') return 'unavailable'
  if (raw !== 'ready' || !connected) return 'connecting' // server hasn't reported the leg — never assume it works
  return active ? 'active' : 'connected'
}

/** Pipeline stage pill. Dot + text label so state is never color-only
 * (DESIGN_SYSTEM.md §7); `active` also lights the border. */
export function StatusPill({ label, state }: { label: string; state: PillState }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.04em] transition-colors duration-300',
        state === 'active' ? 'border-voice-active/50 bg-voice-active/10 text-text-primary' : 'border-border bg-bg-base/40 text-text-secondary',
        state === 'error' && 'border-risk-high/50',
        state === 'unavailable' && 'border-risk-medium/50 bg-risk-medium/10',
      )}
    >
      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', DOT[state])} aria-hidden />
      {label}
      <span
        className={cn(
          'normal-case tracking-normal',
          state === 'active' ? 'text-voice-active-text' : state === 'unavailable' ? 'text-risk-medium-text' : 'text-text-muted',
        )}
      >
        {LABEL_TEXT[state]}
      </span>
    </span>
  )
}

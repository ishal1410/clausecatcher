/**
 * DEMO_DAY_BUGS.md finding 1: the Gemini pill was hard-wired to
 * `connected ? 'connected' : 'connecting'`, so it read a healthy green
 * "ready" whenever the socket was open — even with no Gemini key at all.
 * The claim-check leg now comes off the wire (`status.claim_check`).
 */
import { describe, expect, it } from 'vitest'
import { claimPillState } from './StatusPill'

describe('claim-check pill', () => {
  it('is green only when the server says the checker is ready', () => {
    expect(claimPillState('ready', true, false)).toBe('connected')
    expect(claimPillState('ready', true, true)).toBe('active')
  })

  it('is amber when the checker is disabled and red when it errors', () => {
    expect(claimPillState('disabled', true, false)).toBe('unavailable')
    expect(claimPillState('disabled', true, true)).toBe('unavailable')
    expect(claimPillState('error', true, true)).toBe('error')
  })

  it('never claims ready before the server has reported the leg', () => {
    expect(claimPillState(undefined, true, true)).toBe('connecting')
    expect(claimPillState('ready', false, false)).toBe('connecting')
  })
})

/**
 * DEMO_DAY_BUGS.md finding 1, second half. The Gemini *pill* was fixed to read
 * `status.claim_check` off the wire, but the verdict tile — the biggest thing
 * in the cockpit, and the first thing a judge reads — still derived "Call
 * status: On-contract" from `connected && contradictions === 0` alone. With no
 * Gemini key, or with Gemini failing mid-call, the product therefore announced
 * that the call matched the contract when it had never checked a single line.
 *
 * "On-contract" may only appear when the server says the checker is ready AND
 * no check has failed during this call.
 */
import { describe, expect, it } from 'vitest'
import { callStatus } from './CallVerdict'

describe('call status tile', () => {
  it('says On-contract only when the checker is ready and nothing failed', () => {
    expect(callStatus(true, 0, 'ready', false, false, 3)).toEqual({ label: 'On-contract', tone: 'safe' })
  })

  /**
   * A green "On-contract" before anyone has said anything is a verdict on an
   * empty call: the tile used to read safe from the instant the socket opened,
   * which is the first thing a judge sees in the cockpit.
   */
  it('does not deliver a verdict before a line has been heard', () => {
    expect(callStatus(true, 0, 'ready', false, false, 0)).toEqual({ label: 'Listening', tone: 'unknown' })
  })

  it('reports contradictions even if a later check failed', () => {
    expect(callStatus(true, 2, 'ready', false, false, 4)).toEqual({ label: 'Off-contract', tone: 'risk' })
    expect(callStatus(true, 2, 'ready', true, false, 4)).toEqual({ label: 'Off-contract', tone: 'risk' })
  })

  it('never claims On-contract when the checker is not running', () => {
    for (const state of ['disabled', 'error', undefined] as const) {
      expect(callStatus(true, 0, state, false).label).toBe('Not checked')
      expect(callStatus(true, 0, state, false).tone).toBe('unknown')
    }
  })

  it('never claims On-contract after a check has failed', () => {
    expect(callStatus(true, 0, 'ready', true, false, 3)).toEqual({ label: 'Not checked', tone: 'unknown' })
  })

  it('still shows Connecting before the socket is up', () => {
    expect(callStatus(false, 0, 'ready', false).label).toBe('Connecting')
    expect(callStatus(false, 0, undefined, false).label).toBe('Connecting')
  })

  it('says Ended, not Connecting, once the call is over', () => {
    expect(callStatus(false, 0, 'ready', false, true).label).toBe('Ended')
  })

  /**
   * The disconnect path reopened the original bug: a dropped socket made the
   * tile fall back to the safe styling and the raw line count, so a keyless
   * server that had checked nothing went green the moment the connection
   * died. Nothing that is not verified may ever come back as `safe`.
   */
  it('never returns to safe when the socket drops', () => {
    for (const [claim, failed] of [['disabled', false], ['error', false], [undefined, false], ['ready', true]] as const) {
      expect(callStatus(false, 0, claim, failed).tone).toBe('unknown')
      expect(callStatus(false, 0, claim, failed, true).tone).toBe('unknown')
    }
  })

  it('keeps a contradiction it already found after the socket drops', () => {
    expect(callStatus(false, 2, 'ready', false)).toEqual({ label: 'Off-contract', tone: 'risk' })
    expect(callStatus(false, 2, 'disabled', true)).toEqual({ label: 'Off-contract', tone: 'risk' })
  })
})

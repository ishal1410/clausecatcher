/**
 * useSession.test.ts — regression tests for the transcript reducer.
 *
 * The bug: a server `transcript` message was stored with `final: false`
 * hardcoded, and a final turn was only allowed to replace a partial when it
 * was itself non-final. Live STT (server/main.py on_turn) sends partials and
 * then a final for the same turn, so the pane collapsed to a single line that
 * never settled. These tests pin the fixed behavior.
 */
import { describe, expect, it } from 'vitest'
import { initialState, reducer, type SessionState } from './useSession'
import type { ServerMessage } from '../lib/protocol'

const server = (msg: ServerMessage) => ({ kind: 'server' as const, msg })
const transcript = (text: string, final?: boolean): ServerMessage => ({ type: 'transcript', text, final })

function apply(msgs: ServerMessage[], from: SessionState = initialState): SessionState {
  return msgs.reduce((state, msg) => reducer(state, server(msg)), from)
}

describe('transcript reducer', () => {
  it('replaces the open partial with the final of the same turn', () => {
    const state = apply([transcript('we will knock', false), transcript('we will knock ten percent off', true)])
    expect(state.transcript).toEqual([{ text: 'we will knock ten percent off', final: true }])
  })

  it('keeps the real final flag instead of forcing false', () => {
    const state = apply([transcript('a settled line', true)])
    expect(state.transcript).toEqual([{ text: 'a settled line', final: true }])
  })

  it('starts a new line once the previous one is final', () => {
    const state = apply([
      transcript('first turn', true),
      transcript('second', false),
      transcript('second turn', true),
    ])
    expect(state.transcript).toEqual([
      { text: 'first turn', final: true },
      { text: 'second turn', final: true },
    ])
  })

  it('overwrites an open partial with the next partial', () => {
    const state = apply([transcript('we', false), transcript('we will', false)])
    expect(state.transcript).toEqual([{ text: 'we will', final: false }])
  })

  it('treats a missing final flag as a partial', () => {
    const state = apply([transcript('no flag')])
    expect(state.transcript).toEqual([{ text: 'no flag', final: false }])
  })

  it('does not overwrite a locally simulated line', () => {
    const local = reducer(initialState, { kind: 'local_transcript', text: 'simulated rep line' })
    const state = apply([transcript('live mic partial', false)], local)
    expect(state.transcript).toEqual([
      { text: 'simulated rep line', final: true },
      { text: 'live mic partial', final: false },
    ])
  })
})

/**
 * Session lifecycle — DEMO_DAY_BUGS.md finding 2. The socket closes (demo
 * busy, 60 s idle, 7 min cap, restart) and the cockpit kept showing LIVE,
 * a running timer and "Listening", because `ws.onclose` was a no-op and
 * nothing ever set `connected` back to false.
 */
describe('session lifecycle', () => {
  const report = {
    contract_clauses_referenced: [],
    contradictions: [],
    transcript_count: 0,
    started_at: '2026-09-17T10:00:00Z',
    ended_at: '2026-09-17T10:00:16Z',
    est_cost_usd: 0,
    claim_check_calls: 0,
    claim_check_errors: 0,
  }
  const ended = (reason: string, withReport = true) =>
    ({ type: 'session_ended', reason, ...(withReport ? { report } : {}) }) as unknown as ServerMessage

  it('marks the session ended when the socket closes', () => {
    const open = reducer(initialState, { kind: 'connected' })
    expect(open.connected).toBe(true)
    const closed = reducer(open, { kind: 'disconnected' })
    expect(closed.connected).toBe(false)
    expect(closed.ended).toBe('closed')
  })

  it('reads the demo-busy close code so the judge is told why', () => {
    const closed = reducer(reducer(initialState, { kind: 'connected' }), { kind: 'disconnected', code: 1013 })
    expect(closed.ended).toBe('busy')
  })

  it('keeps the server-sent reason when the socket closes afterwards', () => {
    const idle = apply([ended('idle')])
    expect(idle.ended).toBe('idle')
    expect(idle.report).toEqual(report)
    expect(reducer(idle, { kind: 'disconnected' }).ended).toBe('idle')
  })

  it('carries a report-less end (demo busy) with its reason', () => {
    expect(apply([ended('busy', false)]).ended).toBe('busy')
  })

  it('clears the ended state when a new socket opens', () => {
    const restarted = reducer(apply([ended('time_limit')]), { kind: 'connected' })
    expect(restarted.ended).toBeNull()
    expect(restarted.connected).toBe(true)
  })

  it('stores the claim-check leg reported by status', () => {
    const state = apply([{ type: 'status', stt: 'connected', voice: 'disabled', claim_check: 'disabled' } as unknown as ServerMessage])
    expect(state.status).toEqual({ stt: 'connected', voice: 'disabled', claim_check: 'disabled' })
  })

  it('surfaces check_error to the user', () => {
    const state = apply([{ type: 'check_error', message: 'Contract check unavailable.' } as unknown as ServerMessage])
    expect(state.error).toBe('Contract check unavailable.')
  })
})

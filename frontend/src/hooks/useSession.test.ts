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

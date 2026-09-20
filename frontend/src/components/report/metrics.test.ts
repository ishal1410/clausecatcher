import { describe, expect, it } from 'vitest'
import { callSpan, claimCheckState, flagsBySection, formatClock, positionPct, scoreBand, scoreOf } from './metrics'

const c = (section_number: string, t: string) => ({ sentence: '', literal_text: '', section_number, t })

describe('report metrics', () => {
  it('scores and clamps', () => {
    expect(scoreOf({ transcript_count: 47, contradictions: [c('4.2', ''), c('7.3', '')] })).toBe(96)
    expect(scoreOf({ transcript_count: 0, contradictions: [c('1', ''), c('2', '')] })).toBe(0)
    expect(scoreOf({ transcript_count: 0, contradictions: [] })).toBe(100)
  })

  it('bands at the spec thresholds', () => {
    expect([scoreBand(91), scoreBand(90), scoreBand(70), scoreBand(69)]).toEqual(['clean', 'review', 'review', 'risk'])
    expect(scoreBand(96, 2)).toBe('review')
  })

  it('positions events and survives open or bad timestamps', () => {
    const { start, span } = callSpan({ started_at: '2026-09-15T10:00:00Z', ended_at: '2026-09-15T10:10:00Z' })
    expect(span).toBe(600_000)
    expect(positionPct('2026-09-15T10:05:00Z', start, span)).toBe(50)
    expect(positionPct('2026-09-15T11:00:00Z', start, span)).toBe(100)
    expect(positionPct('garbage', start, span)).toBe(0)
    expect(callSpan({ started_at: '2026-09-15T10:00:00Z', ended_at: null }, Date.parse('2026-09-15T10:00:00Z')).span).toBe(1)
  })

  it('formats clocks and counts flags per section', () => {
    expect(formatClock(125_000)).toBe('02:05')
    expect(formatClock(-5)).toBe('00:00')
    expect(flagsBySection({ contradictions: [c('4.2', ''), c('4.2', ''), c('7.3', '')] })).toEqual(
      new Map([
        ['4.2', 2],
        ['7.3', 1],
      ]),
    )
  })

  /**
   * DEMO_DAY_BUGS.md finding 1+2: the report announced "CLEAN CALL - 100% of
   * lines on-contract" when the claim checker was a stub and nothing was ever
   * compared against the contract.
   */
  it('never bands a call clean when the claim check did not run', () => {
    expect(scoreBand(100, 0, 'ready')).toBe('clean')
    expect(scoreBand(100, 0, 'disabled')).toBe('unchecked')
    expect(scoreBand(100, 0, 'error')).toBe('unchecked')
    expect(scoreBand(50, 3, 'disabled')).toBe('unchecked')
  })

  it('reads the claim-check leg off the report, inferring it on an older server', () => {
    const base = { claim_check_calls: 0, claim_check_errors: 0 }
    expect(claimCheckState({ ...base, claim_check_state: 'ready' })).toBe('ready')
    expect(claimCheckState({ ...base, claim_check_state: 'disabled' })).toBe('disabled')
    expect(claimCheckState({ ...base, claim_check_state: 'error' })).toBe('error')
    // no claim_check_state on the wire: zero successful calls means nothing was checked
    expect(claimCheckState(base)).toBe('disabled')
    expect(claimCheckState({ claim_check_calls: 3, claim_check_errors: 3 })).toBe('error')
    expect(claimCheckState({ claim_check_calls: 3, claim_check_errors: 0 })).toBe('ready')
  })
})

/** Pure report math, kept out of Report.tsx so it can be unit-tested without rendering. */
import type { Report } from '../../lib/protocol'

/** UI_SCREENS_SPEC §5: 100 - contradictions/lines*100, clamped 0..100. */
export function scoreOf(report: Pick<Report, 'transcript_count' | 'contradictions'>): number {
  const total = Math.max(report.transcript_count, 1)
  const raw = 100 - (report.contradictions.length / total) * 100
  return Math.max(0, Math.min(100, Math.round(raw)))
}

export type ScoreBand = 'clean' | 'review' | 'risk'

/** safe above 90, accent 70-90, risk-high below 70. Any contradiction caps the band at 'review':
 *  one false promise is a compliance breach, so the report never calls such a call "clean". */
export function scoreBand(score: number, contradictions = 0): ScoreBand {
  if (score > 90) return contradictions > 0 ? 'review' : 'clean'
  if (score >= 70) return 'review'
  return 'risk'
}

function ms(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? null : t
}

/** Call span in ms; open calls (ended_at null) run to `now`. Never 0, so it's safe to divide by. */
export function callSpan(report: Pick<Report, 'started_at' | 'ended_at'>, now = Date.now()): { start: number; span: number } {
  const start = ms(report.started_at) ?? now
  const end = ms(report.ended_at) ?? now
  return { start, span: Math.max(end - start, 1) }
}

/** Position of an event on the timeline, 0..100. */
export function positionPct(t: string, start: number, span: number): number {
  const at = ms(t)
  if (at === null) return 0
  return Math.min(100, Math.max(0, ((at - start) / span) * 100))
}

/** 125000 -> "02:05"; hours roll into minutes ("75:00") — calls are short. */
export function formatClock(msValue: number): string {
  const total = Math.max(0, Math.round(msValue / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/** section_number -> how many contradictions cited it. */
export function flagsBySection(report: Pick<Report, 'contradictions'>): Map<string, number> {
  const counts = new Map<string, number>()
  for (const c of report.contradictions) counts.set(c.section_number, (counts.get(c.section_number) ?? 0) + 1)
  return counts
}

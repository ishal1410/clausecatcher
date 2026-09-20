/**
 * protocol.ts — TypeScript types for the /ws/session/{id} WebSocket
 * protocol, as implemented in server/main.py. Kept as one file so the two
 * directions (client->server, server->client) stay obviously in sync with
 * the handler in that file.
 */

export interface Clause {
  section_number: string
  title: string
  literal_text: string
}

// -- client -> server ---------------------------------------------------
// Binary frames (raw ArrayBuffer of Int16 PCM16 @ 16000 Hz, ~100ms chunks,
// from public/audio-worklet.js) are sent alongside these JSON messages.

export type ClientMessage =
  | { type: 'transcript'; text: string }
  | { type: 'ask'; section_number: string }
  | { type: 'stop' }

// -- server -> client -----------------------------------------------------

/** The three upstream legs. `claim_check` is 'ready' ONLY when a real Gemini
 *  checker is configured and not killed by CLAUSECATCHER_PAID_DISABLED;
 *  'disabled' means every line goes unchecked, 'error' means configured but
 *  out of budget (process call cap). Never infer it from socket state. */
export interface StatusMessage {
  type: 'status'
  stt: 'disabled' | 'connected' | 'error'
  voice: 'disabled' | 'connected' | 'error'
  claim_check: ClaimCheckState
}

export type ClaimCheckState = 'ready' | 'disabled' | 'error'

/** A line was NOT verified (checker off, failed, quota/cap reached).
 *  Server-rate-limited to at most one per 20 s per session; the message is
 *  human-readable and carries no upstream error text. */
export interface CheckErrorMessage {
  type: 'check_error'
  message: string
}

export interface TranscriptMessage {
  type: 'transcript'
  text: string
  final?: boolean
}

export interface AlertMessage {
  type: 'alert'
  section_number: string
  title: string
  literal_text: string
  sentence: string
  t: string
}

export interface ClauseMessage extends Clause {
  type: 'clause'
}

export interface AgentSpeakingMessage {
  type: 'agent_speaking'
  state: 'start' | 'stop'
}

export interface AgentAudioMessage {
  type: 'agent_audio'
  pcm16_b64: string
  sample_rate: number
}

export interface ErrorMessage {
  type: 'error'
  message: string
}

export interface Report {
  /** 'disabled'/'error' here means 0 contradictions proves nothing: the lines
   *  were never checked. Only 'ready' makes "clean call" an honest headline. */
  claim_check_state: ClaimCheckState
  contract_clauses_referenced: string[]
  contradictions: Array<{
    sentence: string
    section_number: string
    literal_text: string
    t: string
  }>
  transcript_count: number
  started_at: string
  ended_at: string | null
  est_cost_usd: number
  claim_check_calls: number
  claim_check_errors: number
  [extra: string]: unknown
}

export interface SessionEndedMessage {
  type: 'session_ended'
  report: Report
}

export type ServerMessage =
  | StatusMessage
  | TranscriptMessage
  | AlertMessage
  | ClauseMessage
  | AgentSpeakingMessage
  | AgentAudioMessage
  | ErrorMessage
  | CheckErrorMessage
  | SessionEndedMessage

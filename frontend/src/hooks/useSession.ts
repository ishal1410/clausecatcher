/**
 * useSession.ts — WebSocket session lifecycle + reducer state for the
 * ClauseCatcher live call. Ported from the WS-handling half of web/app.js
 * (connectWs/handleServerMessage/startMicCapture/playAgentAudioChunk),
 * behavior unchanged, now typed and React-shaped.
 *
 * Contract/consent/report-fetch REST calls stay in src/lib/api.ts and are
 * called directly by screens (e.g. App.tsx) — this hook owns only the
 * session_id -> WebSocket lifecycle: connect, mic capture in, agent audio
 * playback out, and the reducer state screens render from.
 */
import { useCallback, useReducer, useRef } from 'react'
import { base64ToInt16Array, int16ToFloat32, nextScheduleTime, rmsLevel } from '../lib/dsp'
import type { Clause, ClientMessage, Report, ServerMessage } from '../lib/protocol'

export interface TranscriptLine {
  text: string
  final: boolean
}

export interface AlertRecord {
  section_number: string
  title: string
  literal_text: string
  sentence: string
  t: string
}

interface SessionState {
  connected: boolean
  status: { stt: string; voice: string } | null
  transcript: TranscriptLine[]
  alerts: AlertRecord[]
  clauses: Clause[]
  agentSpeaking: boolean
  report: Report | null
  error: string | null
}

const initialState: SessionState = {
  connected: false,
  status: null,
  transcript: [],
  alerts: [],
  clauses: [],
  agentSpeaking: false,
  report: null,
  error: null,
}

type Action =
  | { kind: 'reset' }
  | { kind: 'connected' }
  | { kind: 'server'; msg: ServerMessage }
  | { kind: 'local_transcript'; text: string }
  | { kind: 'ws_error'; message: string }

function reducer(state: SessionState, action: Action): SessionState {
  switch (action.kind) {
    case 'reset':
      return initialState
    case 'connected':
      return { ...state, connected: true }
    case 'local_transcript':
      return { ...state, transcript: [...state.transcript, { text: action.text, final: true }] }
    case 'ws_error':
      return { ...state, error: action.message }
    case 'server': {
      const msg = action.msg
      switch (msg.type) {
        case 'status':
          return { ...state, status: { stt: msg.stt, voice: msg.voice } }
        case 'transcript': {
          const final = !!msg.final
          const lines = state.transcript
          const last = lines[lines.length - 1]
          if (!final && last && !last.final) {
            return { ...state, transcript: [...lines.slice(0, -1), { text: msg.text, final: false }] }
          }
          return { ...state, transcript: [...lines, { text: msg.text, final }] }
        }
        case 'alert':
          return {
            ...state,
            alerts: [
              {
                section_number: msg.section_number,
                title: msg.title,
                literal_text: msg.literal_text,
                sentence: msg.sentence,
                t: msg.t,
              },
              ...state.alerts,
            ],
          }
        case 'clause':
          return { ...state, clauses: [...state.clauses, { section_number: msg.section_number, title: msg.title, literal_text: msg.literal_text }] }
        case 'agent_speaking':
          return { ...state, agentSpeaking: msg.state === 'start' }
        case 'agent_audio':
          return state // audio is handled imperatively (playback), not stored in state
        case 'error':
          return { ...state, error: msg.message }
        case 'session_ended': {
          // server may end a session without a report (e.g. reason "busy",
          // error "demo busy, try again shortly") -- surface the error, don't crash
          const ended = msg as typeof msg & { reason?: string; error?: string }
          return { ...state, report: ended.report ?? null, error: ended.error ?? state.error }
        }
        default:
          return state
      }
    }
    default:
      return state
  }
}

export function useSession() {
  const [state, dispatch] = useReducer(reducer, initialState)

  const wsRef = useRef<WebSocket | null>(null)
  const callActiveRef = useRef(false)
  const agentSpeakingRef = useRef(false)

  const micStreamRef = useRef<MediaStream | null>(null)
  const micContextRef = useRef<AudioContext | null>(null)
  const workletNodeRef = useRef<AudioWorkletNode | null>(null)
  const micLevelRef = useRef(0)

  const playbackCtxRef = useRef<AudioContext | null>(null)
  const playbackNextStartRef = useRef(0)
  const agentLevelRef = useRef(0)

  const [levels, setLevels] = useReducer(
    // ponytail: returning prev on sub-1% change skips the re-render; throttle to ~20 Hz if still hot
    (prev: { mic: number; agent: number }, next: { mic: number; agent: number }) =>
      Math.abs(prev.mic - next.mic) < 0.01 && Math.abs(prev.agent - next.agent) < 0.01 ? prev : next,
    { mic: 0, agent: 0 },
  )

  const stopMicCapture = useCallback(() => {
    const node = workletNodeRef.current
    if (node) {
      node.port.onmessage = null
      node.disconnect()
      workletNodeRef.current = null
    }
    if (micContextRef.current) {
      micContextRef.current.close().catch(() => {})
      micContextRef.current = null
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop())
      micStreamRef.current = null
    }
    micLevelRef.current = 0
  }, [])

  const stopPlayback = useCallback(() => {
    if (playbackCtxRef.current) {
      playbackCtxRef.current.close().catch(() => {})
      playbackCtxRef.current = null
      playbackNextStartRef.current = 0
    }
    agentLevelRef.current = 0
  }, [])

  const startMicCapture = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    })
    micStreamRef.current = stream
    const ctx = new AudioContext()
    micContextRef.current = ctx
    await ctx.audioWorklet.addModule('/audio-worklet.js')
    const source = ctx.createMediaStreamSource(stream)
    const node = new AudioWorkletNode(ctx, 'mic-downsampler')
    workletNodeRef.current = node
    node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      const int16 = new Int16Array(event.data)
      micLevelRef.current = rmsLevel(int16)
      setLevels({ mic: micLevelRef.current, agent: agentLevelRef.current })
      if (!callActiveRef.current || agentSpeakingRef.current) return // don't transcribe our own agent's voice
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(event.data)
    }
    // Don't connect the worklet to destination — we only want to read mic
    // data, not play it back (that would echo the caller to themselves).
    source.connect(node)
  }, [])

  const playAgentAudioChunk = useCallback((base64: string, sampleRate: number) => {
    if (!playbackCtxRef.current) {
      playbackCtxRef.current = new AudioContext({ sampleRate })
      playbackNextStartRef.current = playbackCtxRef.current.currentTime
    }
    const ctx = playbackCtxRef.current
    const int16 = base64ToInt16Array(base64)
    agentLevelRef.current = rmsLevel(int16)
    setLevels({ mic: micLevelRef.current, agent: agentLevelRef.current })
    const float32 = int16ToFloat32(int16)
    const buffer = ctx.createBuffer(1, float32.length, sampleRate)
    buffer.copyToChannel(float32 as Float32Array<ArrayBuffer>, 0)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)
    const startAt = nextScheduleTime(playbackNextStartRef.current, ctx.currentTime)
    source.start(startAt)
    playbackNextStartRef.current = startAt + buffer.duration
  }, [])

  const send = useCallback((msg: ClientMessage) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
  }, [])

  const start = useCallback(
    (sessionId: string) => {
      // close any previous socket first: an orphan keeps paid upstreams open server-side
      const prev = wsRef.current
      if (prev) {
        prev.onopen = prev.onmessage = prev.onerror = prev.onclose = null
        prev.close()
      }
      stopMicCapture()
      stopPlayback()
      dispatch({ kind: 'reset' })
      callActiveRef.current = true
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${proto}//${location.host}/ws/session/${sessionId}`)
      wsRef.current = ws

      ws.onopen = () => {
        dispatch({ kind: 'connected' })
        startMicCapture().catch((err: Error) => {
          dispatch({ kind: 'ws_error', message: `Microphone unavailable: ${err.message}. Use "Simulate rep line" instead.` })
        })
      }

      ws.onmessage = (event: MessageEvent) => {
        if (typeof event.data !== 'string') return // server only sends JSON text frames
        let msg: ServerMessage
        try {
          msg = JSON.parse(event.data)
        } catch {
          return
        }
        if (msg.type === 'agent_speaking') agentSpeakingRef.current = msg.state === 'start'
        if (msg.type === 'agent_audio') playAgentAudioChunk(msg.pcm16_b64, msg.sample_rate || 24000)
        dispatch({ kind: 'server', msg })
        if (msg.type === 'session_ended') ws.close()
      }

      ws.onerror = () => dispatch({ kind: 'ws_error', message: 'Connection to ClauseCatcher server had an error.' })

      ws.onclose = () => {
        // no-op: reducer state already reflects status; UI reads `connected`
      }
    },
    [startMicCapture, playAgentAudioChunk, stopMicCapture, stopPlayback],
  )

  const stop = useCallback(() => {
    callActiveRef.current = false
    agentSpeakingRef.current = false
    send({ type: 'stop' })
    stopMicCapture()
    stopPlayback()
    // onmessage closes on session_ended (report delivered); this backstop covers a server that never sends it
    const ws = wsRef.current
    if (ws) window.setTimeout(() => ws.close(), 2000)
  }, [send, stopMicCapture, stopPlayback])

  const sendSimulate = useCallback(
    (text: string) => {
      if (!text.trim()) return
      send({ type: 'transcript', text })
      dispatch({ kind: 'local_transcript', text })
    },
    [send],
  )

  const sendAsk = useCallback((sectionNumber: string) => send({ type: 'ask', section_number: sectionNumber }), [send])

  return {
    state,
    micLevel: levels.mic,
    agentLevel: levels.agent,
    start,
    stop,
    sendSimulate,
    sendAsk,
  }
}

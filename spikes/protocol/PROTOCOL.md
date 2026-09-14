# ClauseCatcher Protocol Spec — AssemblyAI Voice Agent API + Streaming

Authoritative, source-driven. Every claim below is either a **direct quote + URL**
from AssemblyAI's official docs (fetched via WebFetch, 2026-09-13), or explicitly
marked **NOT DOCUMENTED**. Nothing here is inferred silently.

Sources fetched:
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/events-reference
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/tools/overview
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/tools/http-tools
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/tools/client-side-tools
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/browser-integration
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/create-agent
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/turn-detection-and-interruptions
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/quickstart
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/prompting-guide
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/deploy
- https://www.assemblyai.com/docs/streaming
- https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket
- https://www.assemblyai.com/pricing
- https://github.com/AssemblyAI (voice-agent-starter-python, voice-agent-starter-js, streaming-self-hosting-stack)

---

## Q1. Can the agent speak PROACTIVELY (backend injects, no user utterance)?

**ANSWER: YES — documented, two mechanisms, both outside of tool-call/hold-mode.**

Source: `voice-agent-api/events-reference`

1. **`reply.create`** — "Generate immediate agent response":
   ```json
   {"type": "reply.create", "instructions": "..."}
   ```
   Quoted use case: *"Useful for status updates during tool execution without user
   input triggering it."* Nothing in the docs restricts this to tool-call context —
   the event itself is a general client→server event, listed independently of the
   tool-call flow.

2. **`conversation.message`** — "Inject context without user speaking":
   ```json
   {"type": "conversation.message", "role": "user", "content": "..."}
   ```
   Quoted: *"Does not auto-trigger a reply."* — so to make the agent speak after
   injecting context you must follow it with `reply.create`.

Both events are documented on the main events-reference page, not buried inside
the hold-mode tool-call section — the WebFetch extraction explicitly separated
"Key Capabilities: Backend-initiated speech — `reply.create` and
`conversation.message` enable agent responses without user utterances" as a
first-class capability of the protocol.

**Practical proactive-speak sequence (derived from documented events, not
independently demonstrated in a single doc example):**
```json
{"type": "conversation.message", "role": "user", "content": "The rep just said the price is $500/month."}
{"type": "reply.create", "instructions": "Ask the rep to confirm the exact price and contract length."}
```
NOT DOCUMENTED: whether `reply.create` can be sent with an empty/no `instructions`
field, or whether repeated `reply.create` calls without a user turn in between are
rate-limited or rejected.

---

## Q2. One connection or two? Listen-only / no-auto-reply option?

**ANSWER: NOT DOCUMENTED — no listen-only / no-auto-reply / manual turn_detection
mode found anywhere in the Voice Agent API docs.** Checked three separate pages
specifically for this and all three came back negative:

- `turn-detection-and-interruptions` — full schema quoted:

  | Field | Purpose (quoted) |
  |---|---|
  | `vad_threshold` | "Speech detection sensitivity (`0.0` to `1.0`). Lower is more sensitive." |
  | `min_silence` | "Minimum silence for a confident end-of-turn, in ms. Left unset, the agent paces this adaptively." |
  | `max_silence` | "Maximum silence before forcing end-of-turn, in ms. Left unset, the agent paces this adaptively." |
  | `interrupt_response` | "Set `false` to disable barge-in entirely." |
  | `interruption_delay` | "How long after the user starts speaking, in ms, before a barge-in can interrupt the agent." |

  There is no `mode`/`type` enum (no `manual`, `server_vad`, `none`,
  `push-to-talk`) documented on this object. Extraction verdict: *"No listen-only
  mode documented: the schema provides no native configuration to prevent
  auto-reply or keep the agent silent unless directly addressed through
  `turn_detection` parameters."*

- `prompting-guide` — searched specifically for "stay silent unless addressed" /
  multi-party monitoring guidance. Verdict: *"there is no guidance about making
  the agent stay silent unless directly addressed, not replying to every
  utterance, listen-only behavior, or monitoring multi-party conversations."*

- `quickstart` — no mention of multiple participants/roles in a session or
  listen-only mode.

Additionally, `events-reference`'s `conversation.message` schema only shows a
single `"role": "user"` value in its example — the docs give no evidence of a
documented multi-participant/multi-role conversation model (e.g. a "rep" role vs
a "monitor" role) inside one session.

**CONCLUSION for ClauseCatcher: the two-connection architecture is the only
documented-safe path.** Nothing in the fetched docs supports "one Voice Agent
session takes continuous rep audio and silently monitors, replying only to a
separate monitor." The empirically-testable alternative (system-prompt
instruction to stay silent + rely on `turn_detection.max_silence`/never firing
`reply.create` automatically) is a **prompting workaround, not a protocol
guarantee** — the model could still auto-reply to rep speech because
`turn_detection` has no documented off-switch. Treat "system prompt says stay
silent" as unverified until tested (see TEST_PLAN.md Q2).

Recommended architecture per docs: plain **Streaming v3 STT** session for the
rep's continuous audio (cheap, $0.15–0.45/hr, no LLM/TTS attached) + a separate
**Voice Agent API** session for the monitor's Q&A, fed by transcript text from
the streaming session via `conversation.message` (Q1 mechanism) as needed. This
is the only combination fully backed by documented events.

---

## Q3. Tool type: client-side function tools vs HTTP tools

**ANSWER: DOCUMENTED — both exist, exact shapes below.**

Source: `tools/overview`, `tools/http-tools`, `tools/client-side-tools`

Quoted distinction (`tools/overview`):
- HTTP Tools: *"Defined on your stored agent. You give a URL and a parameter
  list; AssemblyAI makes the request for you and feeds the result to the
  model."*
- Function Tools: *"Declared inline in `session.tools`. The agent emits a
  `tool.call`; your code runs the logic and sends back a `tool.result`."*

### 3a. Client-side function tool (no public URL — over the same websocket)

Definition, in `session.update` → `session.tools` (`tools/client-side-tools`):
```json
{
  "type": "function",
  "name": "get_weather",
  "description": "Get current weather for any city. Use this whenever the user asks about weather.",
  "parameters": {
    "type": "object",
    "properties": {"location": {"type": "string", "description": "City name, e.g. London"}},
    "required": ["location"]
  },
  "execution_mode": "interactive",
  "timeout_seconds": 120
}
```

Agent → Client (`tool.call`):
```json
{
  "type": "tool.call",
  "name": "get_weather",
  "call_id": "...",
  "arguments": {...}
}
```

Client → Agent (`tool.result`):
```json
{
  "type": "tool.result",
  "call_id": "...",
  "result": "{...}"
}
```
Quoted constraint: *"Send `tool.result` when `reply.done` is the latest event
you've received." Sending results earlier or later breaks turn-taking
mechanics.* (`tools/client-side-tools`)

Events-reference gives a slightly fuller `tool.result` shape including an error
flag:
```json
{"type": "tool.result", "call_id": "...", "result": "{...}", "is_error": false}
```

### 3b. HTTP tool (requires a public HTTPS URL — AssemblyAI's backend calls it)

Definition, on the stored agent (`tools/http-tools`):
```json
{
  "name": "get_weather",
  "description": "Get current weather for a location. Use this whenever the user asks about weather, temperature, or conditions.",
  "parameters": {
    "type": "object",
    "properties": {
      "latitude": {"type": "number", "description": "Latitude in decimal degrees, e.g. 48.85."},
      "longitude": {"type": "number", "description": "Longitude in decimal degrees, e.g. 2.35."}
    },
    "required": ["latitude", "longitude"]
  },
  "execution_mode": "interactive",
  "timeout_seconds": 30,
  "http": {
    "url": "https://api.example.com/weather",
    "http_method": "GET",
    "headers": [
      {"name": "Authorization", "value": "Bearer <secret>"}
    ]
  }
}
```
Quoted requirement: *"requests to private, loopback, or link-local addresses are
blocked"* and only `https` endpoints are permitted (`tools/http-tools`). This
confirms HTTP tools categorically need a publicly reachable HTTPS endpoint —
client-side function tools do not, since the call/result round-trips over the
already-open websocket.

Argument mapping (quoted): GET/DELETE → query string; POST/PUT/PATCH → JSON
body. Headers are `{name, value}` pairs, auth values "write-only" and
"encrypted at rest."

**Execution modes** (both tool types share `execution_mode`, from
`tools/overview`):
- `interactive` — "Agent speaks a transition phrase, emits `tool.call`, client
  processes asynchronously, then sends `tool.result`."
- `hold` (referred to as "Hold mode" in the doc) — "Agent goes silent on
  `tool.call`; client sends `tool.result` to auto-trigger the next reply."

For ClauseCatcher (no public HTTPS endpoint available for a spike): **use
client-side function tools.** This is the documented no-public-URL path.

---

## Connection facts (all questions)

### Voice Agent API
- Websocket URL: `wss://agents.assemblyai.com/v1/ws`
  (Source: `browser-integration`)
- Auth: **token as query parameter**, not a header:
  ```js
  wsUrl.searchParams.set("token", token);
  const ws = new WebSocket(wsUrl);
  ```
  Token obtained via `GET /v1/token` with `Authorization: Bearer ${API_KEY}`.
  (Source: `browser-integration`)
- Audio input format: PCM16, **24 kHz**, base64-encoded, sent as JSON:
  ```js
  ws.send(JSON.stringify({ type: "input.audio", audio: b64 }));
  ```
  (Source: `browser-integration`; corroborated by `events-reference`:
  `{"type": "input.audio", "audio": "<base64-encoded PCM16>"}`)
- Session end: `{"type": "session.end"}` — quoted: *"Stops billing immediately;
  the session becomes non-resumable."* (Source: `events-reference`)
- Session resume: `{"type": "session.resume", "session_id": "sess_abc123"}` —
  "Sessions persist for 30 seconds after disconnection." (Source:
  `events-reference`)
- Billing/auto-close: quoted, `deploy`: *"Skipping `session.end` leaves the
  session in a 30-second grace window that you pay for."*
- Speaker labels on Voice Agent API: **NOT DOCUMENTED.** `create-agent`
  extraction explicitly notes: *"The documentation does not explicitly detail
  billing mechanics, session auto-close behavior, or speaker diarization
  features"* — checked and confirmed absent from the config-field list on that
  page (only `input.format`, `input.keyterms`, `output.voice`, `output.volume`,
  `turn_detection.*` were found).

### Streaming v3 (STT-only, no LLM/TTS)
- Websocket URL: `wss://streaming.assemblyai.com/v3/ws` (Source: `docs/streaming`)
- Auth: **`Authorization` header, no `Bearer` prefix** — direct API key.
  (Source: `docs/streaming`, `streaming-websocket`)
- Audio input: binary frames (not base64) — quoted example:
  `ws.send(chunk, websocket.ABNF.OPCODE_BINARY)`. Default "mono 16-bit PCM";
  also supports AAC (ADTS) and Opus (`ogg_opus`/`opus`). Sample rate is
  configurable via `sample_rate` param to match source audio. (Source:
  `docs/streaming`)
- `UpdateConfiguration` message, exact JSON (Source: `streaming-websocket`):
  ```json
  {
    "type": "UpdateConfiguration",
    "prompt": "A contextual prompt describing what the audio is about...",
    "keyterms_prompt": ["AssemblyAI", "Krabby Patty"],
    "min_turn_silence": 700,
    "max_turn_silence": 1600,
    "agent_context": "Sure — what date would you like to book?"
  }
  ```
- `keyterms_prompt`: quoted — *"A list of words and phrases to improve
  recognition accuracy for. Maximum 100 terms."*
- Session end message: `{"type": "Terminate"}` (Source: `streaming-websocket`)
- Speaker labels: **DOCUMENTED, available in Streaming v3** — quoted: *"Whether
  to enable Streaming Speaker Diarization. When enabled, each Turn event will
  include a `speaker_label` field and each final word in the `words` array will
  include a `speaker` field for word-level speaker attribution."* Params:
  `speaker_labels` (boolean), `max_speakers` (integer, 1-10). (Source:
  `streaming-websocket`)
- Inactivity/duration limits: quoted — inactivity-timeout param "integer,
  minimum 5, maximum 3600 [seconds] ... If not set, no inactivity timeout is
  applied." Plus a hard cap: "Sessions have a maximum duration of 3 hours
  before forced disconnect." (Source: `streaming-websocket`)

### Speaker labels — Voice Agent vs Streaming summary
| Path | Speaker labels | Source |
|---|---|---|
| Voice Agent API | NOT DOCUMENTED (absent from full config field list) | `create-agent` |
| Streaming v3 | DOCUMENTED — `speaker_labels`, `max_speakers`, `speaker_label` field on Turn events | `streaming-websocket` |

This is direct evidence supporting the Q2 recommendation: if ClauseCatcher needs
per-speaker attribution on the rep's audio, Streaming v3 is the documented path;
Voice Agent API does not document this capability at all.

### Billing figures (for TEST_PLAN.md budgeting)
- Voice Agent API: **"$4.50/hr ($0.075/min)"** — quoted, `pricing`. All-inclusive
  STT+LLM+TTS+orchestration, billed per session minute.
- Streaming: **"$0.45/hr base"** (Universal-3.5 Pro Realtime) vs **"$0.15/hr"**
  (Universal-Streaming) — quoted, `pricing`. "Billing is per WebSocket session
  duration, not audio duration sent."
- Free credits: **"$50 in free credits"** at signup, no credit card required
  (quoted, `pricing`).

### GitHub quickstart repos (real code, not fetched in full — task allows
citing repo existence; no live API key available to run them)
- https://github.com/AssemblyAI/voice-agent-starter-python — "An AssemblyAI
  voice agent is one JSON file: publish it, talk to it in the browser, then put
  it on a Twilio phone number. Python, standard library only."
- https://github.com/AssemblyAI/voice-agent-starter-js — same pattern, Node,
  zero dependencies.
- https://github.com/AssemblyAI/streaming-self-hosting-stack — "AssemblyAI
  streaming self-hosting resources and examples."

---

## Summary table

| Question | Verdict |
|---|---|
| Q1: Proactive speak | **DOCUMENTED** — `reply.create` + `conversation.message` (events-reference), not tied to tool/hold-mode |
| Q2: Listen-only / single-session dual-role | **NOT DOCUMENTED** — no turn_detection mode, no multi-role conversation model found across 3 targeted pages; two-connection architecture (Streaming v3 for rep + Voice Agent for monitor) is the only documented-safe design |
| Q3: Tool shapes | **DOCUMENTED** — client-side function tool (`tool.call`/`tool.result` over websocket, no public URL) vs HTTP tool (needs public HTTPS, blocks private/loopback/link-local); exact JSON above |

---

## Event names audit (2026-09-13)

**Trigger:** an independent verifier grepped this file for the three event
names `voice_agent/spike_voice_agent.py` uses as its "user speech was
processed" signal (`transcript.user`, `transcript.user.delta`,
`input.speech.started`) and found **zero matches** — those names appeared
nowhere in PROTOCOL.md before this section. A prior fixer had claimed they
were documented here; that claim was false *for this file*. This section
re-verifies all of them (and every other `"type"` string the .py file sends
or matches) directly against AssemblyAI's official docs and, where possible,
official example code, and records them here so the grep now finds them.

Sources fetched (2026-09-13, via WebFetch):
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/events-reference
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/browser-integration
- https://github.com/AssemblyAI/voice-agent-starter-python (`lib.py`, via `curl` of the raw file — no `WebFetch` HTML rendering; confirmed **not** relevant: this file only wraps the `/v1/agents` REST API for publishing an agent, it does not open or handle the Voice Agent websocket itself, so it has no `"type"` event strings to cross-check)

### Full server→client event list (events-reference, verbatim)

| Event | Quoted description |
|---|---|
| `session.ready` | "Session is established and ready to receive audio." |
| `session.updated` | "Sent after `session.update` is applied successfully." |
| `session.ended` | "Final event emitted on every clean teardown" |
| `input.speech.started` | "Turn detection determined the user has started speaking." |
| `input.speech.stopped` | "Turn detection determined the user has stopped speaking." |
| `transcript.user.delta` | "Partial transcript of what the user is saying" — schema `{"type": "transcript.user.delta", "item_id": "item_abc123", "text": "What's the weather in"}`; quoted caveat: *"`text` is the **full transcript so far**, not an incremental chunk."* |
| `transcript.user` | "Final transcript of the user's utterance." — schema `{"type": "transcript.user", "text": "What's the weather in Tokyo?", "item_id": "item_abc123"}` |
| `reply.started` | "Agent has begun generating a response." |
| `reply.audio` | "A chunk of the agent's spoken response as base64 PCM16." |
| `transcript.agent.delta` | "Word-level streaming of the agent's response" |
| `transcript.agent` | "Full text of the agent's response" |
| `reply.done` | "Agent has finished the reply." |
| `tool.call` | "Agent wants to call a registered tool." |
| `session.error` | "Session or protocol error." |

### Full client→server event list (events-reference, verbatim)

| Event | Quoted description |
|---|---|
| `input.audio` | "Stream PCM16 audio to the agent." |
| `session.update` | "Configure the session." |
| `session.resume` | "Reconnect to an existing session using the `session_id`" |
| `session.end` | "End the session cleanly." |
| `tool.result` | "Send a tool result back to the agent." |
| `reply.create` | "Ask the agent to generate a reply right now" |
| `conversation.message` | "Inject a message into the conversation context" |

**On the generic `"error"` type (used at spike_voice_agent.py:233, 258, 340,
466 as `t in ("session.error", "error")`):** `events-reference`'s formal
event list documents only `session.error` — WebFetch checked specifically and
reported: *"Not found. The documentation contains only `session.error` as an
error event type; there is no distinct event with `{"type": "error"}`."*
However, `browser-integration`'s example message handler defensively checks
**both**:
```javascript
} else if (msg.type === "session.error" || msg.type === "error") {
  log("Error: " + msg.message);
}
```
So `"error"` is not a formally documented event name, but AssemblyAI's own
browser-integration example treats it as a possible one. Verdict: **keep the
defensive check** (matches official example code) but treat `session.error`
as the only formally-specified error event. Mark `"error"` **UNVERIFIED as a
protocol-level event**, verified only as appearing in one official example's
defensive coding.

### `conversation.message` — `role` field (corrects PROTOCOL.md:96-99 above)

Full field table, quoted (`events-reference`):

| Field | Type | Description |
|---|---|---|
| `role` | string | `"user"` or `"system"`. |
| `content` | string | The message text to add to the conversation. |

**CORRECTION:** the original Q2 section above (lines 96-99) states *"the
docs give no evidence of a documented multi-participant/multi-role
conversation model"* and that the schema "only shows a single `"role":
"user"` value in its example." That was accurate about the *example JSON*
but incomplete about the *field table* — the field table (not fetched when
Q2 was written) documents exactly two allowed values: `"user"` and
`"system"`. This does **not** overturn the Q2 conclusion (there is still no
documented per-role behavior difference, no third "monitor"/"rep" role, and
no listen-only/`turn_detection` off-switch) — it only corrects the narrower
claim about how many `role` values are documented.

### Does an injected `conversation.message` (role `"user"`) produce an echoed transcript/speech event?

**NOT DOCUMENTED.** The only documented effect, quoted verbatim
(`events-reference`):
> "Inject a message into the conversation context without the user speaking
> it. Useful for seeding context or replaying prior history. This does not
> by itself make the agent reply; send `reply.create` if you want an
> immediate response."

This explicitly rules out an *automatic reply*. It says nothing — in either
direction — about whether the server also emits `transcript.user`,
`transcript.user.delta`, or `input.speech.started` as a side effect of the
injection. No page fetched (events-reference, browser-integration,
quickstart) shows an example pairing `conversation.message` with any
resulting transcript/VAD event, and none states such events are suppressed
for injected (non-audio) messages either.

**Consequence for spike_voice_agent.py `test_proactive` (Q1):** the risk
flagged by the task — that if the server echoes the injected message as a
`transcript.user`-shaped event, `saw_user_speech` would flip `True` and Q1
would false-FAIL — is a **live, undocumented risk**, not ruled out by any
source found. It can only be resolved empirically (run Q1 once and inspect
`raw_event_types` in the result JSON for a `transcript.user`/
`transcript.user.delta`/`input.speech.started` immediately after the
`conversation.message` send), not from docs. Recorded here as UNVERIFIED
per this skill's rules — no name or behavior is invented to fill the gap.

### Table: every `"type"` string in `voice_agent/spike_voice_agent.py` vs docs

(Grepped read-only from the file; file itself not edited — voice_agent
ownership is out of scope for this edit.)

| Name in code | Where (line) | Sent or matched | Documented? | Correct name if different |
|---|---|---|---|---|
| `session.update` | 136 | sent | YES — events-reference, "Configure the session." | same |
| `session.end` | 144 | sent | YES — events-reference, "End the session cleanly." | same |
| `session.ready` | 138 | matched | YES — events-reference, "Session is established and ready to receive audio." | same |
| `input.audio` | 177 | sent | YES — events-reference, "Stream PCM16 audio to the agent." | same |
| `conversation.message` | 241 | sent | YES — events-reference, "Inject a message into the conversation context" | same |
| `reply.create` | 245 | sent | YES — events-reference, "Ask the agent to generate a reply right now" | same |
| `reply.started` | 229, 252 | matched | YES — events-reference, "Agent has begun generating a response." | same |
| `reply.audio` | 231, 254 | matched | YES — events-reference, "A chunk of the agent's spoken response as base64 PCM16." | same |
| `reply.done` | 260, 468 | matched | YES — events-reference, "Agent has finished the reply." | same |
| `session.error` | 233, 258, 340, 466 | matched | YES — events-reference, "Session or protocol error." | same |
| `error` | 233, 258, 340, 466 | matched | UNVERIFIED as a formal protocol event — not in events-reference's list; appears only in browser-integration's example `onmessage` handler (`msg.type === "session.error" \|\| msg.type === "error"`) | keep as defensive fallback only; do not treat as equal-confidence to `session.error` |
| `input.speech.started` | 250 | matched | YES — events-reference, "Turn detection determined the user has started speaking." | same |
| `transcript.user` | 250 | matched | YES — events-reference, "Final transcript of the user's utterance." | same |
| `transcript.user.delta` | 250 | matched | YES — events-reference, "Partial transcript of what the user is saying" (text field is cumulative, not incremental — see quote above) | same |
| `transcript.agent` | 256, 464 | matched | YES — events-reference, "Full text of the agent's response" | same |
| `tool.call` | 461 | matched | YES — events-reference, "Agent wants to call a registered tool." | same |
| `tool.result` | 449 | sent | YES — events-reference, "Send a tool result back to the agent." | same |

**Bottom line:** every event name `spike_voice_agent.py` sends or matches on
is a real, officially documented AssemblyAI Voice Agent API event name
(cross-checked against `events-reference` and, for the error/transcript/
session.ready names specifically, corroborated by `browser-integration`'s
own example `onmessage` handler using the identical strings). The prior
fixer's claim that these names were "documented" was true of AssemblyAI's
actual API — it was false only in the narrow, literal sense that this file,
PROTOCOL.md, had never recorded them; that gap is what this section closes.
The one open item is NOT a naming error: it's the undocumented
`conversation.message`→echo-event question above, which remains a live risk
in `test_proactive` (Q1) that only a live run can settle.

---

## Live-run doc check (2026-09-13)

**Trigger:** a live run of `voice_agent/spike_voice_agent.py` (2026-09-13,
~22:08 UTC) against `wss://agents.assemblyai.com/v1/ws`. One session sending
only `conversation.message` + `reply.create` (no audio format override)
worked. Two sessions that additionally sent `session.update` with
`"input": {"format": {"encoding": "audio/pcm", "sample_rate": 16000}}` and
then streamed base64 PCM16 mono 16kHz audio via `input.audio` got
`{"type":"session.error","code":"internal_error","message":"Internal service
error"}` and WebSocket close code `1011`. All three sessions logged "expected
session.ready, got session.updated". This section re-verifies the relevant
docs against that observed behavior, read-only, via WebFetch on
2026-09-13.

Sources fetched (2026-09-13):
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/api-spec/create-agent
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/events-reference
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/quickstart
- https://status.assemblyai.com
- https://www.assemblyai.com/changelog (and `/docs/voice-agents/voice-agent-api/changelog`, 404)

### 1. Input audio format — encodings, sample rate, JSON path, pacing

Source: `api-spec/create-agent`, location `AgentCreateRequest.input.format`
(`AudioFormat` schema).

- Allowed `encoding` values (exact strings): `"audio/pcm"`, `"audio/pcmu"`,
  `"audio/pcma"`.
- `sample_rate`: integer; example shown is `24000`; quoted: *"Defaults to PCM
  at 24 kHz if omitted."* **No documented min/max/enum constraining
  `sample_rate` to 24000 only, and no documented statement that 16000 is
  valid or invalid** — the schema does not enumerate allowed sample-rate
  values at all, only gives 24000 as the example/default-when-omitted.
- Channel count: not specified anywhere in the schema (mono is assumed, not
  documented for the Voice Agent API specifically — see PROTOCOL.md's
  existing note on this in `spike_voice_agent.py`'s own header comment).
- Chunk size / message size / pacing guidance: **NOT DOCUMENTED.** WebFetch
  on `api-spec/create-agent`, `voice-agent-api` (overview), and `quickstart`
  all came back with no chunk-size, max-message-size, or real-time-pacing
  requirement text found.

JSON path confirmed via `events-reference`'s full `session.update` example
(quoted verbatim below in §6): `session.input.format.encoding`, with
`sample_rate` nested in the same `format` object per the create-agent
schema (`AudioFormat` covers both `encoding` and `sample_rate` together).

### 2. `input.audio` message shape

Source: `events-reference`, quoted verbatim: the base64 audio field is named
`"audio"` — `{"type": "input.audio", "audio": "<base64-encoded PCM16>"}`.
Matches what `spike_voice_agent.py:213-215` sends exactly.

### 3. Event ordering: `session.ready` vs `session.updated`

Source: `events-reference`. Exact quotes:
- On `session.update`: *"Send immediately on WebSocket connect (before
  `session.ready`)"*.
- On `session.ready`: *"Session is established and ready to receive audio.
  Save `session_id`"* — and *"Start sending `input.audio` only after this
  event."*
- On `session.updated`: *"Sent after `session.update` is applied
  successfully"* — documented as the ack for **subsequent** `session.update`
  calls (mid-conversation), not the initial connection handshake.

The docs' own event-flow diagram (re-fetched and reproduced verbatim as
returned by WebFetch) shows, in order: WebSocket connect → client sends
`session.update` → server responds with `session.ready` — i.e. the **first**
reply to the **first** `session.update` is documented to be `session.ready`,
not `session.updated`. The server does not send `session.ready`
automatically on raw connect before any `session.update` is sent.

**Can input format be changed after session start?** Source:
`events-reference`'s per-field mutability notes (quoted): `"greeting"`,
`"session.output.voice"`, and `"session.output.format"` are each stated
*"Immutable after the first update."* `session.input.format` is listed in
the same config-field table but is **not** grouped with the fields
explicitly marked mutable (`session.input.keyterms`,
`session.input.turn_detection`, `session.input.transcription_mode`,
`session.input.transcription_prompt`, `session.output.volume`,
`system_prompt`) — it has no explicit "mutable mid-session" note attached to
it anywhere found. Treated as **set-at-connect-only by omission**, not by an
explicit "immutable" quote naming `input.format` itself — flagged
**UNVERIFIED (weak)**: the absence of a "mutable" label is suggestive, not a
direct quote saying `input.format` cannot change.

**Live-run discrepancy vs. docs:** the docs' diagram says the first
`session.update` should be answered with `session.ready`. All three live
sessions instead logged `"expected session.ready, got session.updated"` —
including the one session that worked end-to-end. Because this happened in
*both* the working and the failing sessions, it is evidence the ordering
deviation itself is **not** what distinguishes success from `internal_error`
— but it IS a live, reproducible deviation from the documented event-flow
diagram, unresolved by any doc fetched. Recorded as **UNVERIFIED /
contradicts documented diagram**, not explained away.

### 4. `internal_error` / close code 1011 — documented meaning and causes

Source: `events-reference`, quoted verbatim: *"If the server cancels the
session due to an internal error, the WebSocket closes with code `1011`
without any `session.error` payload."*

This is the **only** documented statement about `internal_error` found in
any fetched page. **No enumerated list of causes exists in any fetched
source** (create-agent, events-reference, voice-agent-api overview,
quickstart). No retry guidance (backoff, "reconnect and retry", "reduce
payload size") is documented anywhere found for this error. Given that
statement, the live-observed close-1011 *with* a `session.error` payload
present (`code":"internal_error"`) is notable on its own terms: the docs
describe 1011 as arriving **without** a `session.error` payload, but the
live run's context states a `session.error` payload WAS received before the
close. This is a second discrepancy between documented and observed
behavior, distinct from the 16kHz question, and likewise **UNVERIFIED /
contradicts docs** — not resolved by any source fetched.

### 5. Status page / changelog incidents around 2026-09-13

- `status.assemblyai.com`: fetched 2026-09-13. Quoted: *"No incidents
  reported today"* (Sep 13, 2026) and the same for each day back through
  Sep 1, 2026. All services, Streaming API included, shown as *"All Systems
  Operational."* **No incident found** covering this window.
- `https://www.assemblyai.com/docs/voice-agents/voice-agent-api/changelog` —
  404, does not exist at that path.
- `https://www.assemblyai.com/changelog` — page fetched but returned only
  the changelog's general description, no dated entries were retrievable via
  WebFetch's extraction for Aug–Sep 2026. **NOT CONFIRMED either way** —
  could not verify presence or absence of a relevant changelog entry from
  this fetch; flagged UNVERIFIED rather than asserting nothing shipped.

### 6. Field-by-field comparison: `spike_voice_agent.py` vs. docs

Full verbatim `session.update` example reproduced by WebFetch from
`events-reference` (used as the ground truth for the wrapper shape):
```json
{
  "type": "session.update",
  "session": {
    "system_prompt": "You are a concise assistant.",
    "greeting": "Hi! How can I help?",
    "input": {
      "format": { "encoding": "audio/pcm" },
      "turn_detection": { "vad_threshold": 0.5 }
    },
    "output": { "voice": "alba", "format": { "encoding": "audio/pcm" }, "volume": 100 },
    "tools": [ { "type": "function", "name": "get_weather", "description": "Get weather for a city",
      "parameters": { "type": "object", "properties": { "city": { "type": "string" } }, "required": ["city"] } } ]
  }
}
```

| Field | Sent by .py | Documented? (quote + URL) | Mismatch? |
|---|---|---|---|
| `session.update` wrapper | `{"type": "session.update", "session": {...}}` (line 148) | YES — matches the verbatim example above exactly. `events-reference` | None |
| `session.input.format.encoding` | `"audio/pcm"` (line 444/518) | YES — one of 3 documented enum values (`audio/pcm`, `audio/pcmu`, `audio/pcma`). `api-spec/create-agent` | None |
| `session.input.format.sample_rate` | `16000` (WAV's own rate, line 444/518) | Schema is `integer`, example `24000`, *"Defaults to PCM at 24 kHz if omitted."* No documented allowed-value list. `api-spec/create-agent` | **UNVERIFIED** — not confirmed valid, not confirmed invalid; no documented restriction either way |
| `input.audio` → `audio` field | base64 PCM16 chunk (line 213-215) | YES — `{"type": "input.audio", "audio": "<base64-encoded PCM16>"}`. `events-reference` | None |
| `conversation.message` → `role` | `"user"` (line 370) | YES — enum `"user"` \| `"system"`. `events-reference` | None |
| `reply.create` (Q1, line 373) | `{"type": "reply.create"}`, no `instructions` field | Docs' example shows `instructions` populated; whether it is optional/omittable is **NOT DOCUMENTED** (already flagged as such earlier in this file, line 60-62) | UNVERIFIED (pre-existing, not new) |
| Tool def (`test_tool_call`, lines 519-545): `type`, `name`, `description`, `parameters`, `execution_mode: "interactive"`, `timeout_seconds: 120` | as listed | YES — matches `tools/client-side-tools` example shape field-for-field (already verified earlier in this file, §Q3) | None |
| `tool.result` shape | `{"type": "tool.result", "call_id", "result", "is_error": false}` | YES — matches `events-reference`'s flat shape exactly (already verified earlier in this file, §3a) | None |

**No field the .py sends is itself documented as invalid.** The only
candidate explanation with any documentary trace is `sample_rate: 16000`,
and even that trace is an *absence* (no enumerated allowed-values list), not
a positive statement either permitting or forbidding it.

### Verdict on the hypothesis "16 kHz input causes `internal_error`"

**Docs neither support nor contradict this hypothesis directly.** What the
fetched sources actually establish:

- They do **not** document any sample-rate whitelist or restriction — 24000
  is only ever stated as the *default when the field is omitted*, never as
  the *only* accepted value. So there is no documented rule this hypothesis
  would be violating.
- They do **not** document any enumerated cause list for `internal_error` at
  all (§4) — so "wrong sample rate → internal_error" is exactly as
  undocumented as any other candidate cause (wrong chunk size, unsupported
  pacing, malformed nested field, server-side capacity issue, etc.), none of
  which are ruled in or out either.
- The one concrete discrepancy the docs DO surface is that observed behavior
  deviated from the documented event-flow diagram twice: (a) first reply was
  `session.updated` not `session.ready` in every session including the
  working one, and (b) the close-1011 arrived WITH a `session.error` payload
  where docs say close-1011 happens WITHOUT one. Neither deviation
  distinguishes the failing sessions from the working one, since (a)
  happened in all three and (b) is only known from the two failing ones (no
  equivalent data point from the working session, since it never sent
  `session.update` with an audio format at all).
- Because the working session never exercised `input.format` at all (it
  sent only `conversation.message` + `reply.create`, no `session.update`
  audio-format override, no `input.audio` streaming), **the docs give no
  basis to isolate "16 kHz" from "any audio-format override at all" or from
  "streaming `input.audio` at all"** as the actual trigger — those are three
  different, untested variables conflated in the two failing runs.

**Conclusion: UNVERIFIED, both directions.** Confirming or ruling out the
16kHz hypothesis specifically requires an empirical test docs cannot
substitute for — e.g. one session with `sample_rate: 24000` (the only value
docs positively confirm) streaming real `input.audio`, holding every other
variable (format override present, encoding `audio/pcm`, chunking/pacing
identical) constant against the two failing 16kHz runs.

---

## Reply-control doc check (2026-09-13)

**Trigger:** a live probe against `wss://agents.assemblyai.com/v1/ws`
(2026-09-13) with 24 kHz `audio/pcm` input got `session.ready` and 4
`transcript.user` events, but the agent auto-started 4 `reply.started`
events despite a `system_prompt` saying *"Stay completely silent and do not
respond to anything unless the speaker directly addresses you by name."*
With 16 kHz declared instead, `session.ready` never arrived (0/3 sessions).
An earlier note in this file claimed *"`turn_detection` has no listen-only
mode."* This section re-verifies that claim and answers the five questions
posed, read-only, via WebFetch/WebSearch on 2026-09-13. No AssemblyAI API
calls were made for this section — docs/GitHub only.

Sources fetched (2026-09-13):
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/session-configuration
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/turn-detection-and-interruptions
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/events-reference
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/api-spec/voice-agent-websocket
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/volume
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/message-sequence
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/troubleshooting
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/browser-integration
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/audio-format
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/api-spec/create-agent
- https://www.assemblyai.com/docs/streaming/universal-streaming/turn-detection
- https://www.assemblyai.com/docs/streaming/turn-detection
- https://www.assemblyai.com/docs/streaming/label-speakers-and-separate-channels
- https://www.assemblyai.com/docs/streaming/prompting-and-keyterms
- https://www.assemblyai.com/pricing
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/session-history
- WebSearch: `AssemblyAI "reply.cancel" OR "reply.stop" voice agent`
- WebSearch: `AssemblyAI Voice Agent "listen only" OR "manual reply" OR "push to talk"`

### 1. Every documented way to stop the agent auto-replying

| Mechanism | Documented? (quote + URL) | Would it make the agent silent-until-told? |
|---|---|---|
| `turn_detection` disable/off flag | **NOT DOCUMENTED.** Full field list (`session-configuration`, `turn-detection-and-interruptions`): `vad_threshold` (0.0–1.0, sensitivity), `min_silence`/`max_silence` (ms, end-of-turn timing — quoted: *"Setting `min_silence` or `max_silence` turns off the adaptive pacing and entity-aware waiting described above for the rest of the session"*), `interrupt_response` (quoted: *"Set `false` to disable barge-in entirely"*), `interruption_delay` (0–1000 ms). No `mode`/`type` enum, no `none`/`manual`/`server_vad` value exists on this object in either fetched page. | **NO** — `interrupt_response: false` only stops the agent being *interrupted mid-reply*; it does not stop the agent from *starting* a reply after a user turn. There is no field that suppresses reply generation itself. |
| `transcription_mode` | **DOCUMENTED**, but not a reply switch. Three values (`session-configuration`): `"balanced"` (default), `"min_latency"`, `"max_accuracy"` — controls STT speed/accuracy tradeoff only, unrelated to whether a reply is generated. | **NO** |
| A "manual"/"push-to-talk"/"listen-only" session mode | **NOT DOCUMENTED for the Voice Agent API.** WebSearch for the exact terms surfaced only AssemblyAI's separate **Sync API** (HTTP POST, one utterance per request, no WebSocket/session) as the push-to-talk-shaped product — quoted: *"useful for dictation, IVR menus, call routing, push-to-talk, ... as it's a single HTTP POST with no WebSocket or session to manage."* That is a different product, not a mode of the persistent Voice Agent session ClauseCatcher needs. `prompting-guide` (checked in the prior 2026-09-13 section of this file) also has no "stay silent unless addressed" guidance. | **NO** — no equivalent exists inside a single continuous Voice Agent session. |
| Requiring `reply.create` before any reply (i.e., disabling the automatic post-turn reply) | **NOT DOCUMENTED.** `reply.create` exists and is documented (`events-reference`: *"Ask the agent to generate a reply right now, optionally with custom `instructions`"*) as an **additional**, on-demand trigger, layered on top of automatic turn-based replies — nothing in `events-reference`, `session-configuration`, `message-sequence`, or the OpenAPI-shaped `api-spec/voice-agent-websocket` page states that automatic replies can be turned off so that `reply.create` becomes the *only* way to trigger one. | **NO**, not as documented — `reply.create` is additive, not a gate. |
| `reply.cancel` / any way to cancel or interrupt an in-flight reply | **NOT DOCUMENTED as a client-sendable event.** `events-reference` and the OpenAPI-shaped `api-spec/voice-agent-websocket` page were both fetched and grepped specifically for it — full client→server list is exactly: `session.update`, `session.resume`, `session.end`, `input.audio`, `tool.result`, `reply.create`, `conversation.message`. No `reply.cancel`/`reply.stop`/`reply.interrupt`. WebSearch for `"reply.cancel" OR "reply.stop"` confirms: *"there's no explicit documentation of 'reply.cancel' or 'reply.stop' events in the available search results."* The only documented way a reply stops early is **server-initiated barge-in**: when the user starts talking over the agent, the server itself cancels the reply and emits `reply.done` with `status: "interrupted"` (and `transcript.agent` with `interrupted: true`) — the client cannot request this on demand, only `interrupt_response: false`/`true` tunes whether the server will do it automatically. | **NO** — no client-initiated cancel exists; only automatic barge-in cancellation. |
| `output.volume = 0` as a mute hack | **DOCUMENTED as a volume control, NOT as a suppression of generation/streaming.** Quoted (`volume` page): *"Accepts a number from `0` (silent) to `100` (loudest)"*, *"`null` plays at native level."* No fetched page states that `volume: 0` skips LLM generation, skips TTS synthesis, or skips sending `reply.audio` frames — nor does any page state the opposite (that it still generates/streams/bills). This was checked directly on the `volume` page and came back with **no statement either way**. | **PARTIAL / UNVERIFIED** — it would make the agent inaudible to a human listener, but there is no documented basis to claim it stops the reply pipeline (LLM+TTS) from running, and therefore no documented basis to claim it avoids the $4.50/hr all-inclusive billing (`pricing`, quoted in §Billing below) for that reply. Do not rely on it as a cost- or compute-saving mute. |

**Bottom line for #1:** the only two documented levers that touch reply *behavior* at all are `interrupt_response` (server barge-in on/off) and `reply.create` (an extra on-demand trigger). Neither is a gate on the automatic reply that fires after every user turn. This corrects nothing in the earlier note — it confirms it: **"`turn_detection` has no listen-only mode" holds up under re-verification**, and the search widens the same conclusion to `transcription_mode`, `output.volume`, and the full client→server event list — none of them provide one either.

### 2. Can client-side input be paused and resumed without closing the session? Idle/billing implications?

**Pausing/resuming audio input specifically: NOT DOCUMENTED.** `message-sequence`, `browser-integration`, and `events-reference` were each fetched and checked for a pause/mute/stop-sending-audio-then-resume pattern; none describe one. `browser-integration`'s only relevant guidance is about full session teardown, not a pause:
> "Send [`session.end`](/docs/voice-agents/voice-agent-api/events-reference#session-end) first, then close. A bare `ws.close()` (or the browser tearing the socket down on navigation) leaves the session in the 30-second [`session.resume`](/docs/voice-agents/voice-agent-api/events-reference#session-resume) grace window, and that window is billable."
(`voice-agent-api/browser-integration`)

Simply **not sending `input.audio` frames** while keeping the WebSocket open is not documented as prohibited either — no page states a minimum audio cadence or an audio-silence timeout that force-closes the socket. But going quiet does not appear to change turn_detection/reply behavior (see §1): the agent's own reply logic is driven by transcribed user speech, not by the presence/absence of client audio frames, so simply pausing the mic feed is not documented as a silence mechanism either — it only stops new transcripts from being produced, it does not touch whether a reply already in flight, or one requested via `reply.create`, still speaks.

**Idle/billing implications: DOCUMENTED, and idle time is billed.** From the troubleshooting page (`voice-agent-api/troubleshooting`), quoted verbatim under "Unexpected billing after the call ended":
> "Sessions appear to be billed for ~30 seconds longer than the user was actually on the call." — Fix: "Send `session.end` before closing the socket on any intentional disconnect."

And from `deploy` (already in this file, §Connection facts): *"Skipping `session.end` leaves the session in a 30-second grace window that you pay for."* From the pricing page, quoted verbatim and generalized across AssemblyAI's WebSocket-session products:
> "Streaming billing reminder: session duration, not audio duration. A WebSocket open for 60 minutes with 30 minutes of audio sent is billed for 60 minutes." and "Idle time counts. A WebSocket held open for 5 minutes between calls = 5 billable minutes." (`assemblyai.com/pricing`)

No fetched page carves out an exception for the Voice Agent API specifically, and the Voice Agent API's own troubleshooting/deploy pages independently confirm the same "billed while the socket is open, not while audio flows" model for the 30-second grace window. **Conclusion: a held-open, un-paused Voice Agent session is billed for the full time it is open, silence included** — there is no documented "idle discount." No fetched page states an idle *timeout* that auto-closes a Voice Agent session (`session-history` was checked specifically for this and came back with no billing/timeout content at all).

### 3. Sample rates — resolving the audio-format vs. create-agent conflict

`audio-format` page, its encoding/sample-rate table, quoted verbatim:
> "Encoding | Sample rate | Bit depth
> `audio/pcm` | 24,000 Hz | 16-bit signed integer (little-endian)"
(only one row exists for `audio/pcm` — no alternate rate listed in this table; `audio/pcmu`/`audio/pcma` are each listed at 8,000 Hz, 8-bit, in their own rows)

`audio-format` page, the `format.sample_rate` field description, quoted verbatim from its own config-field table:
> "`format.sample_rate` | integer | No | Hz. Determined by the encoding if omitted."

**These two quotes do not actually conflict** — they describe different things. The table row states what `audio/pcm` *is documented as being*: 24,000 Hz, 16-bit. The field-table row describes what happens if you **omit** `sample_rate` from the JSON: it is *"determined by the encoding"* — i.e., omitting it on `audio/pcm` defaults to 24,000 Hz (matching the table), and by the same sentence would presumably default to 8,000 Hz on `audio/pcmu`/`audio/pcma`. Neither quote says `sample_rate` can be *explicitly* set to a non-default value for a given encoding — the `create-agent` OpenAPI schema (`api-spec/create-agent`) types `sample_rate` as a bare `integer` with `example: 24000` and **no `enum`/`minimum`/`maximum`** constraining it, so the schema does not forbid writing `16000` either. **Net: docs describe 24,000 Hz as the value `audio/pcm` has/defaults to, never state 24,000 as the only legal value you may explicitly send, and never state 16,000 is invalid.** The live probe's 16 kHz failure (`session.ready` never arriving, 0/3) is therefore **empirically real but not explained or predicted by any docs text found** — it is evidence beyond the documentation, not a documented restriction. Treat "Voice Agent API input requires exactly 24,000 Hz in practice" as an operational finding from your own probe, distinct from and not contradicted by the docs, which are simply silent on the restriction.

(This matches and extends the prior 2026-09-13 section's finding on `sample_rate: 16000` → `internal_error`, which reached the identical "UNVERIFIED, docs neither confirm nor deny" conclusion for a different failure mode — `internal_error`/close-1011 there, vs. no `session.ready` at all here. Both are consistent with "docs don't document a sample-rate whitelist, but the server enforces one in practice.")

### 4. Streaming STT v3 equivalents (`wss://streaming.assemblyai.com/v3/ws`)

- **Speaker diarization/labels** — DOCUMENTED. Quoted (`streaming/label-speakers-and-separate-channels`): *"Enable Streaming Diarization by adding `speaker_labels: true` to your connection parameters."* Fields: `speaker_labels` (boolean) — *"Set to `true` to enable real-time speaker diarization"*; `max_speakers` (integer, 1–10) — *"Hard cap on the number of speaker labels."* Each `Turn` event carries a `speaker_label` field (e.g. `A`, `B`); each final word in `words` carries a per-word `speaker` field. Documented limitations, quoted: turns under ~1s of audio are labeled `"PENDING"`; *"When two speakers talk simultaneously, the model cannot split the audio"*; *"The first 1–2 turns of a session may be misassigned."* This matches and is consistent with this file's existing §"Speaker labels — Voice Agent vs Streaming summary" table (line ~292 above), which already recorded Streaming v3 as the only path with documented speaker labels.
- **Keyterms** — DOCUMENTED as `keyterms_prompt`. Quoted (`streaming/prompting-and-keyterms`): *"a maximum of **100 keyterms** per session"*; *"Each individual keyterm string must be **50 characters or less**."* Updatable mid-stream via `UpdateConfiguration` without reconnecting (matches this file's existing quoted `UpdateConfiguration` JSON example above).
- **End-of-turn events** — DOCUMENTED. Quoted (`streaming/universal-streaming/turn-detection` and `streaming/turn-detection`): turn lifecycle is `SpeechStarted` (once per turn) → partial `Turn` messages with `end_of_turn: false` during speech → *"When the turn ends, the session emits a Turn message with `end_of_turn: true`"* (fully formatted, punctuation/casing/entities rendered). Configurable fields: `end_of_turn_confidence_threshold` (default `0.4`) — *"Confidence threshold for semantic end-of-turn. Higher = more confident before ending; lower = ends faster"*; `min_turn_silence`/`min_silence` (default `400`ms in one fetch, `700` in this file's existing `UpdateConfiguration` example — both are the documented "silence before end-of-turn check" field, values differ by fetch/mode, not a contradiction); `max_turn_silence`/`max_silence` (default `1280`ms in one fetch, `1600` in the existing example, same field); `vad_threshold` (default `0.4`). **Manual/forced end-of-turn IS documented here** (unlike the Voice Agent API side): quoted, you can *"send a `ForceEndpoint` event to force a turn boundary"*, or set `end_of_turn_confidence_threshold` to `1` (acoustic-only fallback) or `0` (silence-only, *"not recommended unless you have a custom turn detection model running on top"*). This is Streaming v3-only — Streaming v3 has no reply/LLM/TTS layer at all, so "manual end-of-turn" here only affects when a `Turn` transcript is finalized, not whether anything speaks.
- **Pricing** — see §5 below.

### 5. Pricing — Voice Agent vs. Streaming STT, and idle billing

Quoted verbatim (`assemblyai.com/pricing`):
> "Voice Agent API | **$4.50/hr** ($0.075/min)"
> "Universal-Streaming English | `universal-streaming-english` | **$0.15/hr**"
> "Universal-3.5 Pro Realtime | `u3-rt-pro` (alias `u3-pro`) | **$0.45/hr** base"
> "Diarization, streaming | +$0.12/hr | All streaming models incl. **U3.5 Pro Realtime**"

This matches and reuses the existing §"Billing figures" block already in this file above; nothing new contradicts it. **Does Voice Agent bill while idle/silent?** Per §2 above: yes — no fetched page (pricing, troubleshooting, deploy, session-history) documents an idle/silence carve-out for either product; both are billed "session duration, not audio duration," per the pricing page's own generalized wording, and the Voice Agent-specific troubleshooting/deploy pages corroborate the same model for their own 30-second grace window.

### Verdict

**No.** Nothing fetched from AssemblyAI's official Voice Agent API docs, GitHub, or the OpenAPI-shaped websocket spec documents a way to make a single Voice Agent session listen silently through the whole call and speak only when the client sends `reply.create`. The automatic post-user-turn reply has no documented on/off switch (not `turn_detection`, not `transcription_mode`, not `output.volume`, not any event in the full client→server list), `reply.create` is additive rather than gating, and there is no documented `reply.cancel`/interrupt-on-demand either — only automatic server-side barge-in. This re-confirms rather than overturns the file's existing Q2 conclusion (two-connection architecture: Streaming v3 for the rep's continuous silent-monitoring audio, separate Voice Agent session for the monitor's Q&A) and the earlier "`turn_detection` has no listen-only mode" note, which holds up under this re-verification.

---

## Probe A live results doc check (2026-09-14)

**Trigger:** Probe A's three live runs (2026-09-14, `wss://agents.assemblyai.com/v1/ws`,
24 kHz `audio/pcm`) produced: P1 (12s silence, baseline prompt) → 0
`transcript.user`, 0 `reply.started`; P2 (`vad_threshold:1.0, min_silence:1600,
max_silence:1600, interrupt_response:false, interruption_delay:1000`) →
`session.update` **rejected** with `invalid_value 'input.turn_detection.min_silence'
must be strictly less than 'max_silence'`; P3 (strong "silent note-taker" prompt +
23.5s rep pitch) → 4 `transcript.user`, 4 `reply.started` (agent spoke 4 times
despite the stronger prompt). Read-only doc check, no AssemblyAI API calls —
WebFetch/WebSearch on official docs only, per PROBE_A_SPEC.md's read-only
constraint.

Sources fetched (2026-09-14):
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/api-spec/voice-agent-websocket
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/session-configuration
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/turn-detection-and-interruptions
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/prompting-guide
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/message-sequence
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api
- WebSearch: `AssemblyAI Voice Agent API "auto_response" OR "create_response" OR "response.create" OR text-only output modality`

### 1. Exact documented `turn_detection` schema

Path (confirmed on `api-spec/voice-agent-websocket`, and matches the live
error path `input.turn_detection.min_silence`, which is the session-relative
spelling of the full path): **`session.input.turn_detection`**.

| Field | Type | Range | Default | Unit | Quoted description |
|---|---|---|---|---|---|
| `vad_threshold` | number | 0.0–1.0 | 0.5 | ratio | "Speech detection sensitivity (0.0–1.0). Lower = more sensitive to speech" |
| `min_silence` | integer | 50–10000 | 1000 | ms | "Minimum silence to consider a confident end-of-turn, in milliseconds. **Must be less than `max_silence`.**" |
| `max_silence` | integer | 50–10000 | 3000 | ms | "Maximum silence before forcing end-of-turn, in milliseconds. **Must be greater than `min_silence`.**" |
| `interrupt_response` | boolean | — | true | — | "Whether user speech interrupts the agent. Set `false` to disable barge-in" |
| `interruption_delay` | integer | 0–1000 | per mode | ms | "How long after the user starts speaking...before a barge-in can interrupt" |

(Source: `api-spec/voice-agent-websocket`, exact field-description text quoted
verbatim by targeted re-fetch; corroborated by `session-configuration` and
`turn-detection-and-interruptions`, which give the same field set/ranges but
whose prose versions do **not** themselves spell out the min<max relationship
— `turn-detection-and-interruptions`'s own prose text only says setting
either field "turns off the adaptive pacing and entity-aware waiting," it
does not state the ordering constraint. The ordering constraint is
documented, but only in the OpenAPI-shaped `api-spec` page's field
descriptions, not in the narrative `turn-detection-and-interruptions` page.)

**The `min_silence < max_silence` rule IS documented** (api-spec page, both
directions, quoted above). **P2 sent `min_silence:1600, max_silence:1600`
(equal, not strictly less)** — its rejection is exactly what the documented
constraint predicts, and the live error's field path
(`input.turn_detection.min_silence` / `max_silence`) matches the documented
path. This was a spec-compliance bug in P2's payload, not a discovered
undocumented restriction: PROBE_A_SPEC.md flagged `1600`/`1600` itself as
"UNVERIFIED for applicability" and borrowed from Streaming v3's *different*
`min_turn_silence`/`max_turn_silence` fields, which is why it didn't satisfy
the Voice Agent API's actual (and, it turns out, documented) constraint.

**What each field does to end-of-turn / reply triggering:** `vad_threshold`,
`min_silence`, `max_silence` govern *when a turn is judged to have ended*
(end-of-turn detection only). `interrupt_response`/`interruption_delay`
govern *barge-in* (whether/when the user can cut the agent off mid-reply).
None of the five fields is documented as gating *whether* a reply is
generated after end-of-turn — see §2.

### 2. Documented statement of automatic reply / system_prompt suppression

**No sentence states the agent replies automatically "regardless of
system_prompt."** The closest documented statement is the default-flow
sequence on `turn-detection-and-interruptions`, quoted verbatim:

> "A normal user turn emits [`input.speech.started`] → [`transcript.user.delta`]
> (partials) → [`input.speech.stopped`] → [`transcript.user`] (final) →
> [`reply.started`]. You never signal end-of-turn yourself."
> (`voice-agent-api/turn-detection-and-interruptions`)

This places `reply.started` inside the *default, client-uncontrolled* turn
flow ("you never signal end-of-turn yourself") — it implies automaticity but
does not use the word "automatic," does not say "always," and does not
mention `system_prompt` at all. No page (`message-sequence`,
`turn-detection-and-interruptions`, `prompting-guide`, the API overview page)
contains an explicit "reply happens regardless of prompt content" statement.

**No documented statement says `system_prompt` can suppress replies either.**
`prompting-guide` was fetched specifically for this and returned nothing:
"The page does not state that the system_prompt can suppress/prevent replies
or make the agent stay silent... doesn't address silence/suppression
mechanics." This matches the file's existing §"Reply-control doc check"
conclusion (`turn_detection` has no listen-only mode, `reply.create` is
additive) and is now independently confirmed from the prompting-focused page
instead of only the turn_detection-focused pages. **P3's live result (strong
"never reply" prompt, still 4/4 `reply.started`) is exactly what this
documentation gap predicts** — there is no documented mechanism by which a
system_prompt instruction could have overridden the automatic post-turn
reply, so its failure to do so is consistent with (not contradicted by) the
docs.

### 3. Full documented session field inventory (exhaustive, this fetch)

No `auto_response`, `create_response`, `response.create`, transcription-only
mode, listen-only mode, tool-only mode, or output-modality (text-only/no-audio)
field was found anywhere in the schema, on any page fetched, or via WebSearch
of AssemblyAI's own site content. Full field list found across
`api-spec/voice-agent-websocket` + `session-configuration` (union; where the
two pages disagreed on completeness, the union is listed and each field is
attributed):

**Top-level `session`:**
- `agent_id` (string) — "ID of a stored agent...to bind this session to"
- `system_prompt` (string) — "The agent's personality and context. Can be updated mid-session"
- `greeting` (string) — "What the agent says at the start...Immutable after `session.ready`"
- `input` (object)
- `output` (object)
- `tools` (array)

**`input.*`:**
- `input.format` (object) → `format.encoding` (`audio/pcm` default / `audio/pcmu` / `audio/pcma`), `format.sample_rate` (integer, "Determined by the encoding if omitted")
- `input.keyterms` (array) — "rare or domain-specific terms to boost," max 100 (per `session-configuration`)
- `input.transcription_mode` (`"balanced"` default / `"min_latency"` / `"max_accuracy"`) — per `session-configuration`
- `input.transcription_prompt` (string, max 1750 chars) — per `session-configuration`
- `input.language_codes` (array) — per `session-configuration`
- `input.voice_focus` (`"near-field"` default / `"far-field"`) — per `session-configuration`
- `input.voice_focus_threshold` (0.0–1.0, default 0.85) — per `session-configuration`
- `input.turn_detection` (object) — see §1 table

**`output.*`:**
- `output.voice` (string, default `anna`) — "Voice used for the agent's speech"
- `output.format` (object, same shape as `input.format`)
- `output.volume` (0–100) — "Playback volume...Mutable mid-session"

**`tools[]` item:**
- `type` (string, required, always `"function"`)
- `name`, `description`, `parameters` (JSON Schema)
- `execution_mode` (`"interactive"` default / `"hold"`)
- `timeout_seconds` (1–300, default 120)

`input.transcription_mode`, `input.voice_focus`/`voice_focus_threshold`,
`input.transcription_prompt`, and `input.language_codes` were **not** in this
file's earlier field inventories (the 2026-09-13 "Reply-control doc check"
section listed `transcription_mode` alone, without the other four) — new to
this pass, surfaced by re-fetching `session-configuration` for an exhaustive
list rather than a targeted one. None of the five relate to reply
suppression; they are STT-quality/accuracy tuning knobs (transcription
accuracy mode, background-voice rejection, custom vocabulary prompt, forced
language). This does not change any prior conclusion.

### 4. Does P1 (silence → no reply) prove anything documented?

**No — and this is expected, not new evidence, per the documented event
flow itself.** Per the quoted sequence in §2, `reply.started` is positioned
*after* `input.speech.started` → `transcript.user.delta` → `input.speech.stopped`
→ `transcript.user` in the documented default flow. P1 sent 12s of digital
silence: no speech occurred, so — per that same documented chain — none of
the prerequisite events (`input.speech.started`, any `transcript.user*`)
would fire either, and P1's own result confirms this (0 `transcript.user`
alongside the 0 `reply.started`). **P1 cannot isolate "replies are triggered
by VAD end-of-turn only" from "no reply fires because no turn was ever
detected at all"** — both explanations predict the identical observed
result. This is exactly PROBE_A_SPEC.md's own pre-registered reasoning
(Decision rule 5: *"P1's 0 reply.started result, if PASS, is necessary but
not sufficient for Option A — P1 has no speech in it at all, so it cannot
show whether the agent stays silent while hearing real speech"*) — the doc
check confirms that pre-registered caveat rather than adding new information
beyond it. The only documented fact P1 is consistent with is the ordinary,
undisputed claim that `reply.started` is downstream of turn detection, not
upstream of it (§2 quote) — it says nothing about whether a reply can be
*suppressed* once a turn *is* detected (that question is answered, negatively,
by P3 and by §2's field inventory, not by P1).

### Verdict

Docs give a fully-specified, versioned `turn_detection` schema (§1) — the
`min_silence < max_silence` rule IS documented, in the OpenAPI-shaped
`api-spec` page only, and P2's rejection matches it exactly (spec-compliance
bug in the probe payload, not an undocumented server restriction). No
document states replies are automatic "regardless of `system_prompt`"
verbatim, but the only documented default flow places `reply.started`
inside the client-uncontrolled turn sequence, and no document states
`system_prompt` (or any of the 15 additional fields inventoried in §3) can
suppress it. **No documented field, mode, or combination allows a single
Voice Agent session to receive transcripts without also auto-replying** —
this re-confirms, unchanged, the file's existing Q2 / "Reply-control doc
check" conclusion: the two-connection architecture (Streaming v3 for
listen-only transcription + a separate Voice Agent session for replies)
remains the only documented-safe design for ClauseCatcher.


# ClauseCatcher Protocol Test Plan

Empirical tests to convert PROTOCOL.md's documented answers into verified
behavior. No API key was available while writing this plan — nothing here has
been run. Every test session is capped so total spend stays well under $1
against the $50 free credit.

Rates used (from PROTOCOL.md, quoted from `assemblyai.com/pricing`):
- Voice Agent API: $4.50/hr = $0.075/min = $0.00125/sec
- Streaming (Universal-Streaming): $0.15/hr = $0.0025/min = $0.0000417/sec
- Streaming (Universal-3.5 Pro Realtime): $0.45/hr = $0.0075/min = $0.000125/sec

---

## Test Q1 — Proactive speech via `reply.create` / `conversation.message`

**Goal:** confirm the agent speaks without any prior user audio/utterance.

**Steps:**
1. `GET /v1/token` with `Authorization: Bearer <API_KEY>` to get a temp token.
2. Open `wss://agents.assemblyai.com/v1/ws?token=<token>`.
3. Send:
   ```json
   {"type": "session.update", "session": {"system_prompt": "You are a test agent.", "greeting": null}}
   ```
4. Wait for `session.ready`. **Do not send any `input.audio`.**
5. Send:
   ```json
   {"type": "reply.create", "instructions": "Say exactly: PROACTIVE TEST OK"}
   ```
6. Listen for `reply.started` → `reply.audio` chunks → `transcript.agent` →
   `reply.done`.
7. Separately, test `conversation.message` alone (new session or after step 6):
   ```json
   {"type": "conversation.message", "role": "user", "content": "The rep said the price is $500."}
   ```
   then confirm **no** `reply.started` fires within 5 seconds (per doc:
   "Does not auto-trigger a reply"), then send `reply.create` with
   `instructions: "Summarize what you just heard."` and confirm it now speaks
   correctly referencing the injected content.
8. Send `{"type": "session.end"}` immediately after.

**PASS:** `reply.started`/`reply.audio`/`transcript.agent` appear after step 5
with zero prior `input.audio` frames sent, AND step 7 shows no auto-reply after
`conversation.message` alone but a correct contextual reply after the
follow-up `reply.create`.

**FAIL:** `session.error`, or no `reply.*` events after `reply.create`, or the
agent replies before `reply.create` is sent in step 7 (would mean
`conversation.message` auto-triggers contrary to docs).

**Max session length:** 60 seconds wall clock (connect, 2 exchanges, disconnect).

**Estimated cost:** 60s × $0.00125/sec = **$0.075**.

---

## Test Q2 — Listen-only / single-session dual-role feasibility

Docs found nothing (PROTOCOL.md Q2), so this test empirically checks the
fallback hypothesis: can a system prompt suppress auto-reply to a stream of
"rep" utterances while still answering an explicit "monitor" question, in ONE
Voice Agent session?

**Steps:**
1. Open one Voice Agent session as in Q1.
2. `session.update` with:
   ```json
   {"type": "session.update", "session": {"system_prompt": "You are silently observing a conversation between a sales rep and a customer. Do NOT respond to anything said unless the speaker explicitly says the word MONITOR followed by a question. Otherwise stay completely silent — do not speak.", "greeting": null, "input": {"turn_detection": {"max_silence": 3000}}}}
   ```
3. Stream ~10s of synthetic rep speech as `input.audio` (any short PCM16/24kHz
   WAV, e.g. a TTS'd sentence with no "MONITOR" keyword) with normal pauses.
4. Observe whether `reply.started` fires (it should NOT, per the prompt
   instruction — but PROTOCOL.md flags this as unverified since
   `turn_detection` has no documented off-switch).
5. Stream a second short clip containing "MONITOR, what did the rep just say
   about pricing?"
6. Observe whether `reply.started`/`transcript.agent` fires with a relevant
   answer.
7. `session.end`.

**PASS:** step 4 produces zero `reply.*` events (agent stayed silent on plain
rep speech) AND step 6 produces a correct, relevant reply. This would mean the
system-prompt workaround is viable and ClauseCatcher can use ONE session.

**FAIL (expected, given no documented listen-only mode):** step 4 produces a
`reply.started`/`reply.audio` event on ordinary rep speech (model auto-replies
despite the prompt instruction). If FAIL: adopt the two-connection design from
PROTOCOL.md — Streaming v3 session for continuous rep audio (cheap, STT-only,
optional `speaker_labels`) + a separate Voice Agent session opened only when
the monitor asks a question, fed the relevant transcript slice via
`conversation.message` + `reply.create` (per Q1 mechanism).

**Also test the fallback design directly (run regardless of above result), to
have both data points in one session budget:**
1. Open a Streaming v3 session (`wss://streaming.assemblyai.com/v3/ws`,
   `Authorization: <API_KEY>` header, binary PCM frames).
2. Send `UpdateConfiguration` with `speaker_labels`-relevant params if exposed
   at connect time (check `StreamingSessionBegins`/initial config for
   `speaker_labels`/`max_speakers` — PROTOCOL.md notes these were found on the
   websocket reference; confirm exact placement — connect-time param vs
   `UpdateConfiguration` field — during this test since the fetched page did
   not show `speaker_labels` inside the specific `UpdateConfiguration` JSON
   block quoted).
3. Stream ~15s of two-speaker synthetic audio, confirm `Turn` events include
   `speaker_label`.
4. `{"type": "Terminate"}`.

**Max session length:** Voice Agent leg 30s + Streaming leg 20s = 50s total.

**Estimated cost:** Voice Agent 30s × $0.00125/sec = $0.0375; Streaming 20s ×
$0.0000417/sec (Universal-Streaming rate) ≈ $0.0008. **Total ≈ $0.038.**

---

## Test Q3 — Tool shapes: client-side function tool vs HTTP tool

**Goal:** confirm the client-side `tool.call`/`tool.result` round-trip works
with no public URL, since ClauseCatcher has none in the spike environment.
(HTTP tool test is optional/deferred — it requires standing up a public HTTPS
endpoint, out of scope for a no-API-key spike; document as such rather than
skip silently.)

**Steps (client-side function tool only — the buildable path today):**
1. Open a Voice Agent session.
2. `session.update` with:
   ```json
   {
     "type": "session.update",
     "session": {
       "system_prompt": "When asked for the current clause count, call get_clause_count.",
       "tools": [
         {
           "type": "function",
           "name": "get_clause_count",
           "description": "Returns the number of contract clauses flagged so far.",
           "parameters": {"type": "object", "properties": {}, "required": []},
           "execution_mode": "interactive",
           "timeout_seconds": 30
         }
       ]
     }
   }
   ```
3. `reply.create` with `instructions: "Ask the user how many clauses have been flagged."` — or directly send a `conversation.message` simulating the user asking "how many clauses so far?" then `reply.create`.
4. Wait for `tool.call` event: `{"type":"tool.call","name":"get_clause_count","call_id":"...","arguments":{}}`.
5. Reply with (only after `reply.done` is the latest event received, per
   documented constraint):
   ```json
   {"type": "tool.result", "call_id": "<same call_id>", "result": "{\"count\": 3}", "is_error": false}
   ```
6. Confirm agent speaks a response incorporating "3".
7. `session.end`.

**PASS:** `tool.call` fires with matching `name`/`call_id`, and after
`tool.result` the agent's spoken/`transcript.agent` output references the
value `3`.

**FAIL:** no `tool.call` fires, or `session.error` on the `tool.result` (e.g.
sent before `reply.done`, violating the documented turn-taking constraint —
retry once respecting the ordering rule before declaring FAIL).

**HTTP tool path:** mark **NOT TESTED / DEFERRED** — requires a publicly
reachable HTTPS endpoint (docs confirm private/loopback/link-local URLs are
blocked), which the spike environment does not have. If needed later, stand up
a tunnel (e.g. ngrok) and repeat with an `http` block per PROTOCOL.md Q3
example; budget an extra 30s / $0.0375 for that follow-up test.

**Max session length:** 45 seconds.

**Estimated cost:** 45s × $0.00125/sec = **$0.05625**.

---

## Total planned spend

| Test | Est. cost |
|---|---|
| Q1 | $0.075 |
| Q2 | $0.038 |
| Q3 | $0.056 |
| **Total** | **≈ $0.17** |

Well under the $1 budget and the $50 free credit. All three tests can be run
in a single sitting once an API key is available; total wall-clock session
time ≈ 155 seconds across all connections.

## Preconditions before running any of this

- Valid `ASSEMBLYAI_API_KEY` in environment.
- None of these tests have been executed — this file is a plan, not a report.
- Re-verify `UpdateConfiguration`'s exact field placement for `speaker_labels`/
  `max_speakers` at connect time vs mid-stream before Test Q2's fallback leg —
  PROTOCOL.md flags that the fetched `UpdateConfiguration` JSON example did not
  itself include `speaker_labels`, only the separate quoted sentence about Turn
  events did. Confirm placement empirically, don't assume.

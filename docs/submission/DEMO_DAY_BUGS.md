# Demo-day bug hunt — what breaks when a lablab judge clicks ClauseCatcher

Adversarial pass at HEAD `a629536`. The judge model: opens a hosted URL in an unknown
browser, clicks for ~2 minutes, may deny the microphone, gives up fast.

**How this was tested.** The real app, built `frontend/dist`, served by uvicorn on a local
port with `ASSEMBLYAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY` and
`CLAUSECATCHER_CLAIM_CHECK` removed from the process (no billing — and the keyless path is
itself a judge scenario). Driven with Playwright across Chromium, Firefox and WebKit.
Upstream-outage was simulated by pointing `server.stt.AAI_WS_URL` / `server.voice.TOKEN_URL`
at a dead local port with a fake key — zero network egress. Timeouts were reproduced on a
second instance with `CLAUSECATCHER_IDLE_TIMEOUT_S=8`, `CLAUSECATCHER_SESSION_CAP_S=25`.

Screenshots referenced below live in the run scratchpad
(`…/scratchpad/demoday/`); every one was opened and read, not just captured.

**No code was changed.** Patches are proposed, not applied.

---

## Ranked findings

| # | Severity | Finding | Judge bounces? |
|---|----------|---------|----------------|
| 1 | **Critical** | Claim-check disabled/quota-dead → UI shows a green "Gemini check ready" pill and a confident "On-contract / CLEAN CALL, 100%" verdict while zero checks ran | **Yes — this is the product's one claim** |
| 2 | **Critical** | Socket closes (demo-busy cap, 60 s idle, 7 min cap, restart) but the cockpit stays "LIVE"; typing then appends fake transcript lines and increments "Lines checked" | **Yes** |
| 3 | **High** | Below 1024 px there are no controls at all, "End call" is clipped off-screen at 820 px, labels truncate to `LI… C… R…` | **Yes, on a phone or iPad** |
| 4 | **High** | The mic-denied explanation self-destructs after 5 s and nothing persistent replaces it; the orb keeps saying "Listening" | Likely |
| 5 | Medium-High | The same error renders twice (two toast systems); in WebKit the two overlap into unreadable text, and raw JS error strings reach the judge | Maybe |
| 6 | Medium | "Ask a clause aloud" produces no visible output without a voice key | Maybe |
| 7 | Medium | Cold start on a sleeping free instance is a blank screen with no "waking up" message | Maybe |
| 8 | Medium | Reload mid-call silently dumps to the landing page; Back leaves the app entirely | Maybe |
| 9 | Low-Med | Cockpit doesn't fill the viewport — ~700 px of dead space at 820 px, ~180 px at 1366×768 | No, but it reads unfinished |
| 10 | Low | Keyboard: first Tab in the cockpit is "End call"; no skip link; landmarks unnamed | No |

---

## 1. CRITICAL — the product says "clean call" when it never checked anything

> **Fixed in two passes.** `967bb25` put the claim-check leg on the wire and made
> the Gemini pill and the end-of-call report honest. A second pass on 2026-09-20
> closed the half that was missed: `CallVerdict` derived "Call status: On-contract"
> from `connected && contradictions === 0` alone, so the biggest tile in the
> cockpit still announced the call matched the contract when nothing had been
> checked, and "Lines checked" counted transcript finals rather than checks.
> `callStatus()` now requires `claim_check === 'ready'` and no `check_error` this
> call before it will say On-contract, otherwise it reads "Not checked" with an
> em dash for the count; `useSession` latches `checkFailed` because a line that
> was never checked stays unchecked. `Cockpit` was also never passing
> `claimCheck` to `TopBar`, so the pill sat on "connecting" all call. Pinned by
> `CallVerdict.test.ts` (5 cases) and confirmed in a real browser with the
> checker off: the tile reads "Not checked".


**What the judge sees.** Types the money line into "Simulate rep line" —
*"We can knock ten percent off the price for you."* — presses send. The line appears in the
transcript, **Lines checked: 1**, **Contradictions: 0**, **Call status: On-contract**, and the
top bar's middle pill reads a healthy green **"GEMINI CHECK · ready"**. End the call and the
report announces **"CLEAN CALL — 100% of lines on-contract."**

Nothing was checked. `get_claim_checker()` returned the stub.

**Repro.** Start the server without `GEMINI_API_KEY`/`GOOGLE_API_KEY`/`CLAUSECATCHER_CLAIM_CHECK`
(or with a key whose free-tier quota is spent, or with `CLAUSECATCHER_PAID_DISABLED=1`).
Load demo contract → consent → go live → simulate the discount line.
Screenshots: `02-simulate-after-send.png`, `05-report-after-endcall.png`.

**Cause.**
- `server/claim_check.py:249-254` — no key, or kill switch on, silently returns
  `_stub_claim_checker`, which always answers `unclear`. Logged once server-side, never sent
  to the client.
- `server/main.py:529` — the `status` frame carries only `stt` and `voice`. The claim-check
  leg has no wire representation at all.
- `frontend/src/components/cockpit/TopBar.tsx:86` — the Gemini pill is hard-wired to
  `connected ? … : 'connecting'`. It is green whenever the socket is open, regardless of
  whether Gemini exists.
- `server/main.py:408-413` — a Gemini error/timeout/429 increments `claim_check_errors` and
  returns. The client is never told; it looks identical to "checked, all clean."

**Why it's the worst one.** Every other failure looks like a failure. This one looks like a
*pass*. A judge who types the one line from your own demo script and is told the call is
100% on-contract concludes the detection is fake.

**Smallest fix.** Put the claim-check leg on the wire and refuse to render a verdict when it
is off.

```python
# server/main.py, next to stt_status/voice_status (~line 493)
claim_status = "disabled" if claim_checker is _stub_claim_checker else "connected"
...
await send({"type": "status", "stt": stt_status, "voice": voice_status, "claim_check": claim_status})
```
```python
# server/main.py handle_turn, after the checker runs (~line 412)
if result.get("error"):
    session.claim_check_errors += 1
    await send({"type": "check_error", "message": "Contract check unavailable (upstream error) — this line was not checked."})
```
Then in `TopBar.tsx:86` drive the pill from `status.claim_check` exactly like the other two
(`toPillState(claimCheck, connected, geminiActive)`), and in `CallVerdict` render
`Not checked` instead of `On-contract` when `claim_check !== 'connected'`. Same guard on the
report headline.

---

## 2. CRITICAL — the session dies and the cockpit keeps pretending it's live

> **Partially fixed, and the earlier claim was too strong.** `11f5dc0` clears
> `ws_attached` on disconnect, but `finish()` also calls `end_session()`, which
> sets `ended_at`, and the connect guard rejects any session with `ended_at`
> set. So reconnecting to the *same* session id still fails. What is actually
> true: the `cc_ws` cookie survives, so the contract and consent are intact and
> starting a fresh call is one click - the judge does not lose the upload flow.
> The cockpit no longer claims to be live, which was the reported bug. Full
> mid-call resumption is not implemented.


**What the judge sees.** Three separate paths land here:

- **Third visitor** (`CLAUSECATCHER_MAX_LIVE_WS=2`): server sends `demo busy, try again
  shortly` and closes with 1013. A toast shows it for 5 s, then vanishes. The cockpit sits
  there: red **LIVE** dot, timer counting, pills "connecting", orb "Listening".
  (`03-third-visitor.png`)
- **60 s idle / 7 min cap**: server sends `session_ended`, closes the socket. Cockpit says
  **LIVE 00:16**, "Listening", "On-contract". No banner, no report, no hint.
  (`05-idle-timeout.png`)
- Same after a server restart or any dropped socket.

Then the judge types into the simulate box. **The line appears in the transcript and "Lines
checked" ticks to 1** — while the socket is closed and the server received nothing.
(`05-ghost-type-after-timeout.png`)

**Repro.** `CLAUSECATCHER_IDLE_TIMEOUT_S=8`, go live, wait 14 s, type a line, send.

**Cause.**
- `frontend/src/hooks/useSession.ts:257-259` — `ws.onclose` is an explicit no-op with a
  comment saying state already reflects it. It does not: `connected` is set true in
  `onopen` (line 234) and never set back to false anywhere.
- `frontend/src/hooks/useSession.ts:276-280` — `sendSimulate` calls `send()` (a silent no-op
  when the socket isn't `OPEN`, line 213-216) and then **unconditionally** dispatches
  `local_transcript`. The UI invents a line the backend never saw.
- `server/main.py:542` — `session_ended` arrives with a full report, and
  `useSession` stores it (`reducer`, `session_ended` case) but `App.tsx` only switches to the
  report screen from `handleEnd`, i.e. only when the judge clicks "End call". A
  server-initiated end is invisible.

**Smallest fix.** Three lines in `useSession.ts` plus one in `App.tsx`:

```ts
// reducer: add
case 'disconnected': return { ...state, connected: false }
// start():
ws.onclose = () => dispatch({ kind: 'disconnected' })
// sendSimulate(): only echo what actually went out
const sent = send({ type: 'transcript', text })      // make send() return a boolean
if (sent) dispatch({ kind: 'local_transcript', text })
else dispatch({ kind: 'ws_error', message: 'Session ended — start a new call to keep testing.' })
```
```tsx
// App.tsx: a server-ended session should show its own report
useEffect(() => { if (session.state.report && page === 'cockpit') setPage('report') }, [session.state.report, page])
```
With `connected: false` the existing UI already does the right thing: the pill flips to
"Offline", the timer stops, the orb drops out of "Listening". One fix, four symptoms.

---

## 3. HIGH — the cockpit is unusable below 1024 px, and it tells you to use a control it hid

**390 px** (`06-cockpit-390x844.png`): the "End call" button overflows the header and wraps
into two clipped lines; stat labels truncate to **"LI…" "C…" "R…"**; clause titles truncate to
**"P…" "R…" "D…" "S…"**; 12 px of horizontal page overflow. No transcript, no ask control, no
simulate box — just the note *"Best viewed on a larger screen during a live call."*

**820 px / iPad portrait** (`06-cockpit-820x1180.png`): **the "End call" button is cut off by
the right edge** — the judge cannot end the call. ~700 px of empty space below the fold.
21 px horizontal overflow. Still no controls.

The kicker: when the mic is denied, the toast reads *"Use 'Simulate rep line' instead"* — and
at these widths the simulate box does not exist. The only offered recovery path is invisible.
Mobile judge = zero interaction possible.

**Cause.** `frontend/src/components/cockpit/Cockpit.tsx:114` (`hidden … lg:block` transcript),
`:129` (`hidden … lg:flex` right rail holding **both** CommandBar controls), `:138` the
`lg:hidden` notice. Tailwind `lg` = 1024 px, so every tablet is in the dead zone.

**Smallest fix.** Don't build a responsive cockpit for a hackathon — just move the one control
the demo needs out of the desktop-only rail:

```tsx
// Cockpit.tsx: render CommandBar once, outside the aside, and let the aside hold only the orb
<div className="border-t border-border/60 p-4 lg:hidden">
  <CommandBar clauses={clauses} onAsk={sendAsk} onSimulate={sendSimulate} />
</div>
```
and change the notice to something honest and useful: *"The full cockpit needs a wider screen —
here's the demo control."* Plus `min-w-0`/`shrink` on the TopBar title group so "End call"
survives at 820 px, and `truncate` removal on the stat labels below `sm`.

---

## 4. HIGH — the microphone explanation deletes itself

**What the judge sees.** Deny the mic (or have no device): a toast reads *"Microphone
unavailable: … Use 'Simulate rep line' instead."* — good copy, correct recovery path. Five
seconds later it is gone forever (`01-micdenied-cockpit.png` → `01-micdenied-after6s.png`).
What remains: **LIVE**, a running timer, an orb captioned **"Listening"**, a transcript pane
saying *"Listening for the call to begin."* Nothing anywhere says the mic is off. A judge who
read the page body first and the toast second never sees the explanation.

**Cause.** `frontend/src/components/cockpit/ErrorToast.tsx:12` (5 s auto-dismiss) and
`frontend/src/components/ui/Toast.tsx:23` (same); the mic failure is recorded only as a
transient `state.error` (`useSession.ts:237`) with no persistent flag. `VoiceOrb`'s
`listening` prop is `connected && !agentSpeaking` (`Cockpit.tsx:102`) — it has no idea whether
a mic exists.

**Smallest fix.** One piece of sticky state:

```ts
// useSession: add `micError: string | null`, set in the startMicCapture catch, cleared on start()
```
Render it where the judge is already looking — swap the orb caption from "Listening" to
**"Mic off — use Simulate rep line ↓"** and point an arrow at the box. Costs one prop.

---

## 5. MEDIUM-HIGH — every error renders twice, and WebKit overlaps them

`App.tsx:127-131` pushes `session.state.error` into `<ToastStack>` (fixed `bottom-4 right-4`,
z-50) **and** `Cockpit.tsx:167` renders `<ErrorToast message={state.error} />` (fixed
`bottom-5 right-5`, z-50). Two toasts, same text, same corner.

In Chromium they land 60 px apart and read like two unrelated errors. In WebKit
(`07-cockpit-webkit.png`) they **overlap exactly** and the text is unreadable. The WebKit run
also surfaces the raw exception to the judge: *"Microphone unavailable: undefined is not an
object (evaluating 'navigator.mediaDevices.getUserMedia')."*

**Smallest fix.** Delete one of them — `ErrorToast` is the redundant one; `App` already owns
toasting. And clamp the message: catch the mic error and map any unknown cause to one
sentence rather than interpolating `err.message` (`useSession.ts:237`).

---

## 6. MEDIUM — "Ask a clause aloud" looks broken without a voice key

Picking §3.1 sends `ask`, the server replies with the full clause
(`<< {"type":"clause","section_number":"3.1",…}` captured on the wire), and the **only** visible
change in the whole UI is the watchlist chip flipping from "Watching" to "Referenced"
(`04-ask-clause-keyless.png`). The clause text is never rendered anywhere; without a voice key
nothing is spoken. The control is the most inviting thing in the rail and it appears inert.

**Cause.** `useSession.ts` reducer `case 'clause'` appends to `state.clauses`, which only
`ClauseRiskMeter` consumes as a status flag. No component renders the returned text.

**Smallest fix.** Render the answered clause where alerts already render — an "asked" card in
`AlertStack` reusing the existing blockquote, with the badge "Read aloud" only when
`status.voice === 'connected'`, otherwise "Voice disabled — text only".

---

## 7. MEDIUM — cold start is a blank screen

A sleeping Render free instance takes ~50-60 s to wake. Simulated with a 15 s stall on the
document request: the judge stares at an empty viewport the entire time, no spinner, no text
(`09-coldstart-4s.png`). Nothing distinguishes "waking up" from "dead link."

`frontend/dist/index.html` ships an empty `<div id="root">` with no fallback markup, no
`<noscript>`, and no background color in the document itself — so the first paint before CSS
is **white**, then the 394 KB `index-*.js` has to parse before anything appears.

**Smallest fix.** Inline a skeleton in `frontend/index.html` — it costs nothing and covers both
the cold-start wait (after the document lands) and slow parsing:

```html
<body style="background:#0e1524;color:#94a3b8;font:15px/1.5 system-ui">
  <div id="root"><div style="display:grid;place-items:center;height:100dvh">
    ClauseCatcher is waking up — this takes up to a minute on the free tier.
  </div></div>
</body>
```
React replaces it on mount. Also worth one line in the lablab submission: *"first load may take
~60 s while the free instance wakes."*

---

## 8. MEDIUM — reload mid-call drops everything; Back leaves the app

Reloading during a live call returns the judge to the **landing page**
(`08-after-reload.png`) — contract gone from the UI, session orphaned, no "you had a call in
progress" anywhere. The workspace cookie survives (`/api/contract` would still answer) but
nothing re-reads it.

The SPA also pushes **no history entries** (`history.length` stays flat from landing to setup,
measured). The Back button therefore leaves ClauseCatcher entirely — for a judge who arrived
from the lablab project page, Back means "return to lablab", ending the evaluation.

**Smallest fix (lazy version).** Don't add a router. On mount, `GET /api/contract`; if it
returns clauses, land on **setup** with the contract pre-loaded instead of the marketing page.
That turns a reload from "lost everything" into "one click back to live," and is ~6 lines in
`App.tsx`.

---

## 9. LOW-MED — the cockpit floats in dead space

`cc-cockpit` is `h-full min-h-[480px]` inside a parent with no height, so it collapses to
content: ~180 px of empty background at 1366×768 (`06-cockpit-1366x768.png`), ~700 px at
820 px. It reads as a broken layout rather than a deliberate one.

**Fix.** `min-h-dvh` on the cockpit root (or `h-dvh` on the page wrapper when `page === 'cockpit'`).

---

## 10. LOW — keyboard and screen-reader gaps

Measured tab order in the cockpit: **`End call` → `#cc-ask` → `#cc-sim` → toast dismiss**. The
first thing a keyboard-only judge reaches, one Tab from page load, is the destructive button.
Focus rings are present and visible on all controls (verified `outline: solid` on each), and
`AlertStack` does carry `aria-live="polite"` (`AlertStack.tsx:56`), so new alerts *are*
announced — credit where due.

Gaps: no skip link on the landing page; `main` / `aside` / `section` landmarks are all unnamed
(no `aria-label`); the status pills and the "Lines checked / Contradictions" counters are not in
any live region, so a screen-reader user gets the alert text but no pipeline state; and the
landing page's tab order repeats "Try the live demo" three times with no distinguishing label.

**Fix.** `aria-label` on the three landmarks, move "End call" after the rail in DOM order (or
give it `tabindex` ordering), and one `aria-label="Try the live demo"`/`"…(footer)"` distinction.

---

## Checked and found fine

Worth recording so nobody re-audits these:

- **Double-clicking "Go live" fast** fires exactly **one** `POST /api/session/start` — the
  button's `starting` guard holds. No orphaned sessions.
- **The report is still reachable after a server-side timeout**: clicking "End call" on a dead
  session renders the report that arrived in the `session_ended` frame
  (`05-idle-then-endcall-report.png`), and the REST fallback in `App.tsx` covers the rest.
- **Firefox and WebKit** both render the landing and cockpit correctly, the WebSocket connects,
  and the simulate path works end to end (`07-cockpit-firefox*.png`, `07-cockpit-webkit*.png`).
  The AudioWorklet path could not be exercised in either (no mic device in the harness; WebKit
  additionally hides `navigator.mediaDevices` on a non-secure origin, which will not apply on the
  HTTPS deploy) — **the worklet remains untested outside Chromium**.
- **Upstream outage with keys present** is handled honestly at the pill level: both AssemblyAI
  pills go red "error", the socket stays up, and the server logs the exception without crashing
  (`02-simulate-after-send.png` on the unreachable-upstream instance). What's missing is a
  sentence for the judge, not error handling.
- No console errors, page errors or failed requests in Chromium or Firefox on any run.
- A blank 390 px landing screenshot in one early run did **not** reproduce on retry (timing
  artifact of screenshotting mid-entry-animation); the mobile landing renders fully within
  ~500 ms. Not counted as a finding.

---

## The five fixes worth doing before submitting

1. **Put the claim-check leg on the wire and stop claiming "on-contract" when it never ran**
   (finding 1). Server sends `claim_check` in the `status` frame + a `check_error` message;
   the pill and the verdict read from it. This is the one that decides whether the judge
   believes the product.
2. **`ws.onclose → connected:false`, and stop echoing simulate lines into a closed socket**
   (finding 2). Four symptoms, one small diff in `useSession.ts`.
3. **Move `CommandBar` out of the `lg:` rail and un-clip "End call"** (finding 3). A judge on
   an iPad currently cannot interact with, or exit, the demo.
4. **Make the mic-off state persistent** — orb caption instead of a 5-second toast — and
   **delete the duplicate toast renderer** (findings 4 and 5).
5. **Inline a cold-start skeleton in `index.html`** and note the wake time in the submission
   (finding 7). Ten lines that stop the first impression being a blank tab.

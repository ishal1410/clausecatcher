# ClauseCatcher — UI Screens Spec

**Design read:** hackathon demo product for a compliance/sales-ops buyer, evidence-first legal-adjacent language, leaning on Tailwind + Motion + a muted navy/slate palette (not AI-glass, not purple). Precision over spectacle: the wow moment is proof-of-accuracy (literal clause quoted verbatim), not particle effects.

**Dials:** `DESIGN_VARIANCE: 6` (asymmetric cockpit, calmer landing) · `MOTION_INTENSITY: 6` (fluid, purposeful, never idle-looping except the live pulse and orb) · `VISUAL_DENSITY: 6` on the cockpit (operational, out of this skill's normal landing scope by necessity), `3` on landing/report.

**Token roles** (mapped by DESIGN_SYSTEM.md): `bg` (page ground), `surface` (card/panel), `accent` (single brand blue, used for links/CTAs/focus), `risk-high` (alert red, alerts and contradictions only), `safe` (verified-green, "spoken verbatim" checks only), `voice` (the agent-speaking color, used only on the orb/waveform so it reads as one distinct signal).

One accent (`accent`) for all normal interactive UI. `risk-high`, `safe`, and `voice` are semantic, not decorative — never used as generic accents.

---

## 1. Information architecture

Single-page app, three linear steps, no router needed (state machine in `app.js`/React state):

```
/            → landing (marketing, static)
/app         → setup → call → report   (one mounted flow, section swap, no URL change per step)
```

`/app` sections map 1:1 to existing DOM: `setup-section` → `call-section` → `report-section` → back to `setup-section` via "New session." This spec keeps that exact state machine; only the visual layer changes.

**Grids**
- 1280×720 (video capture frame): 24px outer margin, 12-col grid, cockpit uses fixed 3-pane `280px / 1fr / 320px` (transcript / alerts / rail), top bar 64px.
- 1920×1080: same ratios scaled, outer margin 48px, max content width 1760px centered.
- Mobile (< 768px): landing stacks to single column. The cockpit is desktop-only surface (it's a live-call operator tool); below 768px show a "Best viewed on desktop during a call" notice with transcript + alerts stacked full-width, voice rail collapses to a sticky bottom bar (orb + status pills only, risk meter and command bar hidden behind a "Details" disclosure).

---

## 2. Landing (`/`)

**Layout:** asymmetric split hero, `DESIGN_VARIANCE 6`. Left column (7/12): eyebrow-free headline + subtext + CTA. Right column (5/12): the mini cockpit preview (see below). Nav is a single-line floating bar, 64px, logo mark + "Try the live demo" button only (no link soup).

**Copy**
- H1 (2 lines max): "Your sales reps go off-script. Your contract doesn't." (`text-5xl md:text-6xl tracking-tight`)
- Subtext (≤ 20 words): "ClauseCatcher listens to live sales calls and speaks the exact contract clause the moment a rep contradicts it."
- Primary CTA: "Try the live demo" (single intent, reused verbatim everywhere else that starts a demo — never "Get started" or "Launch app" elsewhere).

**Mini cockpit preview (right column, React, autoplay loop, ~9s cycle, `whileInView` gated so it only runs when scrolled into view):**
1. 0.0s: a fake transcript line types in char-by-char (`transcript-line` mono, 40ms/char): `"We can also do a verbal discount for a big client."`
2. 1.6s: the phrase "verbal discount" gets a `risk-high`-tinted underline (`background-position` sweep, 300ms, `cubic-bezier(0.16,1,0.3,1)`) — motivation: draw the eye to the exact offending words before the card arrives.
3. 2.0s: an alert card slides up + fades in (`y:16→0, opacity:0→1`, 400ms) showing a real clause quote: `"§4.2 — All discounts require written approval from a sales director."`
4. 4.5s: a "Spoken verbatim" checkmark (`safe`) fades in under the quote.
5. 7.0s: everything fades out (`opacity→0`, 500ms), loop restarts at 0.0s.
Reduced motion: static frame at step 3 only, no loop.

**Trust strip** (directly under hero, own section, not crammed into hero): three short claims in a 3-col row, no eyebrow, no icons-as-decoration — icon (Phosphor, 1.5 stroke) + one line each: "Quotes your contract verbatim, never LLM-paraphrased" / "Nothing runs until the rep gives consent" / "Every alert cites the exact section number." `py-24`.

**"How it works" strip** (separate section below trust strip, so no two consecutive sections share a layout family): 3-step horizontal row, numbered by content not by "Step N" labels — "Streaming transcription" (AssemblyAI Streaming STT) → "Contradiction check" (Gemini claim check against your contract) → "Spoken correction" (AssemblyAI Voice Agent speaks the literal clause). Each: small wordmark-style label for the vendor + one-line caption. No em dash, no filler verbs.

**States:** landing is static marketing; only loading state is the preview loop itself (no network calls). Error state: none (no backend calls from this page).

---

## 3. Contract setup (`/app`, step 1)

**Layout:** centered single column, max-w-2xl, `py-24`, step progress as 3 small dots/labels at top ("Contract" → "Consent" → "Call"), not a full stepper bar.

**Drop zone:** dashed-border card (`surface`, `rounded-2xl`, 2px dashed `accent/30`), 240px tall, centered icon (Phosphor `FileArrowUp`) + "Drop your contract PDF here" + "or" + a plain-text button "browse files" (native `<input type=file accept=application/pdf>` under the hood, styled label). Secondary action below, visually distinct (ghost button): "Use demo contract" — maps to `POST /api/contract/demo`.

**States:**
- Empty: drop zone only, no clause list, status line reads "No contract loaded yet."
- Uploading: drop zone content replaced by a skeleton pulse matching the eventual clause-card shape (3 shimmer bars), status "Reading contract…"
- Error (422/503 from `/api/contract`): inline red text under the drop zone using the exact `detail` string from the API (e.g. "file must be application/pdf"), zone border turns `risk-high`, dismissible.
- Success: drop zone collapses to a compact "contract-loaded.pdf · N clauses" chip; clause cards reveal below.

**Clause reveal:** each `{section_number, title, literal_text}` becomes a card: small mono chip for `section_number` (`bg-surface border`, `rounded-md`, tabular numerals) + `title` as the card heading + `literal_text` truncated to 2 lines in a serif-free quote block. Cards stagger in (`whileInView` per item, `y:12→0, opacity:0→1`, 300ms, 80ms stagger) — motivation: proves each clause was individually extracted, not dumped as one blob.

**Consent step:** its own card, visually separated (not a checkbox buried in a form) — heading "Before we listen," one sentence explaining `POST /api/consent {accepted}` records disclosure, then the checkbox + label "I've disclosed this call is monitored for compliance." Unchecked = the "Start call" button stays disabled with a tooltip-on-hover explaining why (no silent disable).

**Bottom:** primary CTA "Start the call" (disabled until clauses.length > 0 AND consent), full width on mobile, right-aligned pill on desktop.

---

## 4. Live call cockpit (`/app`, step 2) — the video star

**Top bar** (64px, `surface`, sticky, safe-area aware): left: session timer (mm:ss, mono, ticking); center: two status pills bound to `status {stt, voice}` — "STT · connected" / "Voice · connected" (pill fill `safe` when `"ready"`/`"connected"`, neutral gray otherwise, `risk-high` on `"error"`); right: "End call" button (`risk-high` outline, confirms nothing — one click, per existing `handleEndCall`).

**Three-pane body** (`280px / 1fr / 320px`):

**Left — transcript.** Scrolling log of rep lines (`transcript {text, final}`). Partial (interim) lines render at 60% opacity, italic, replaced in place per existing `appendTranscriptLine` logic. When an `alert` arrives, the exact `sentence` substring in the just-finalized transcript line gets a `risk-high` underline sweep (same choreography as the landing preview, 300ms) — this is the single highest-value visual link between "what was said" and "what fired."

**Center — alert stack.** Newest on top (`prepend`, but animated: incoming card `y:-16→0, opacity:0→1`, 350ms `cubic-bezier(0.16,1,0.3,1)`, existing cards shift down via `layout` prop). Each card: heading row `"Contradicts §{section_number} — {title}"`; a mono/citation-style quote block for `literal_text` (left border accent, generous padding, quotation marks real not straight); a line `Rep said: "{sentence}"` in muted text; a `safe`-colored "Spoken verbatim ✓" badge that appears once the server confirms playback (see 4a below); a relative timestamp from `t`. Empty state (no alerts yet): a calm one-line placeholder, "No contradictions yet — clean call so far," `safe`-tinted, not an empty gray box.

**Right rail:**
- **Voice orb** (top): a circular `voice`-colored element, idle = slow 4s breathing scale (`1→1.03→1`, reduced-motion: static), speaking = amplitude-reactive scale/glow driven by decoding `agent_audio.pcm16_b64` RMS per chunk into a `useMotionValue` (never `useState`) feeding `scale` and `opacity` — bound to `agent_speaking {state}` for on/off and to per-chunk amplitude for texture. Label under it: "ClauseCatcher speaking…" shown only while `agentSpeaking` true, otherwise "Listening."
- **Clause-risk meter:** one row per loaded clause (from `/api/contract`), a thin horizontal bar per clause (no filled-background-track comparison bars — use a single dot + label per clause instead: gray dot = untouched, `accent` dot = referenced via ask or contradiction-free mention, `risk-high` dot + pulse = currently contradicted). Lights up the exact clause on `alert.section_number` and on `clause` (ask response).
- **Command bar (⌘K style):** a single input styled as a command palette trigger, `⌘K` hint chip on the right, opens a small dropdown of clause section numbers (from `askSelect` population) — selecting sends `{"type":"ask", section_number}` over WS. Below it, visually separated (different affordance, not the same input): "Simulate rep line" plain text input + send button, labeled explicitly as a demo aid so judges don't mistake it for a real feature — maps to `{"type":"transcript", text}`.

**Loading/disabled states:** before `status` arrives, both pills show "· connecting" (neutral gray, no red). If STT errors mid-call, pill flips to `risk-high` "STT · error" but the cockpit stays usable (simulate input still works) — never block the whole screen on a partial subsystem failure.

### 4a. The alert moment, second by second (0–3s)

- **t=0.0s** — `alert` message arrives. The rep's `sentence` substring in the transcript (already rendered as `final`) gets the `risk-high` underline sweep (left→right background-position animation, 300ms).
- **t=0.3s** — alert card begins its slide-in in the center pane (350ms), risk-meter dot for that `section_number` starts a pulse (`opacity 1→0.4→1`, 3 repeats, then settles solid `risk-high`).
- **t=0.6s** — card fully in place. Focus is now the card (no focus-trap needed, just visual weight: card gets a subtle `risk-high/20` outer ring for 1.2s then settles to neutral border).
- **t≈0.8–2.5s** — `agent_speaking {state:"start"}` arrives; voice orb switches from idle-breathing to amplitude-reactive, label changes to "ClauseCatcher speaking…"; `agent_audio` chunks stream and drive the orb in real time.
- **t≈2.5–3s** — speech ends (`agent_speaking {state:"end"}`), orb returns to idle breathing; once the server-side `say_exactly` result lands (surfaced via the existing alert record, no new message needed — render once available on the card refresh), the "Spoken verbatim ✓" badge fades in under the quote (`opacity 0→1`, 250ms) — this is the proof beat, held for the rest of the card's life, not transient.

Sound/voice sync: the orb amplitude and the "speaking" label are the only sound-reactive visuals; nothing else pulses to audio (avoids visual noise competing with the card).

---

## 5. Report (`/app`, step 3)

**Layout:** centered, max-w-3xl, `py-24`. Single column, no split-header.

**Top:** a compliance score ring (SVG, count-up 0→N over 800ms `ease-out`), computed client-side as `100 - (contradictions.length / max(transcript_count,1) * 100)` clamped 0–100, labeled "{score}% clean call" with sub-line "{contradictions.length} contradiction{s} caught out of {transcript_count} lines." Ring color: `safe` above 90, `accent` 70–90, `risk-high` below 70.

**Contradiction timeline:** horizontal line with a dot per contradiction positioned by relative `t` between `started_at` and `ended_at`; hovering (or tapping on mobile) a dot reveals that contradiction's card below (reuses the cockpit alert-card component verbatim, same visual language, so judges see continuity between "live" and "audit record" — the earlier critique's exact gap). Empty state: full green line, one label "No contradictions in this call."

**Facts row:** small `surface` strip, 4 stat tiles (mono numerals): `est_cost_usd`, `claim_check_calls`, `claim_check_errors`, `transcript_count`. Plain functional labels, no fake precision beyond what the API returns.

**Clause citations:** every section in `contract_clauses_referenced`, each rendered as the same citation-quote-block style as the cockpit, so "what we checked against" is auditable, not just "what broke."

**Export:** "Export PDF" ghost button, visual only per brief (triggers `window.print()` — no new dependency, no fake download link).

**Bottom:** "Start a new session" (single CTA intent, reused label, not "Try again" elsewhere) → `resetForNewSession`.

**States:** loading (report not yet arrived): skeleton ring + skeleton stat tiles, 600ms max expected wait (`session_ended` or the 1.5s REST fallback already in `app.js`). Error: if `fetchReportFallback` throws, show the existing toast, keep report section with a manual "Retry" button substituting for the skeleton.

---

## 6. Anti-slop rules applied

- No purple/AI gradients anywhere; `accent` is a single desaturated blue, `bg`/`surface` stay neutral navy-slate per the existing (already-correct) direction.
- No glassmorphism as a blanket treatment — `backdrop-blur` only on the sticky top bar, nowhere else.
- Density is realistic: the cockpit is genuinely information-dense (it's an operator tool mid-call), landing and report stay airy. No card-ification of the report's stat row beyond one thin strip.
- Zero decorative dots — the only colored dots are the risk-meter (real semantic state) and the timeline (real data points).
- Zero section-number eyebrows, zero "Step 1/2/3" labels, zero scroll cues, zero locale/weather strips, zero version footers.
- One CTA intent per action across the whole flow: "Try the live demo" (start), "Start the call" (begin session), "End call" (stop), "Start a new session" (reset). Never a synonym duplicate.
- Icons: Phosphor Light only, `strokeWidth 1.5`, no Lucide, no hand-rolled SVG.

---

## 7. Build order (single engineer, ~2 days, 6 tasks)

1. **Scaffold + tokens wired** (1.5h) — Vite/React/TS/Tailwind/Motion boots; import DESIGN_SYSTEM.md tokens as Tailwind theme extension; base layout shell (`/` and `/app` section-swap state machine) with no styling yet, just structure matching current `app.js` state transitions.
2. **Landing + mini cockpit preview** (3h) — hero, trust strip, how-it-works strip, autoplay preview component (the fake transcript→alert→checkmark loop). This is standalone and reusable as a visual proof point even if the cockpit runs late.
3. **Setup screen** (2.5h) — drop zone, upload/demo REST calls, clause card stagger reveal, consent card, step dots.
4. **Cockpit shell + WS wiring** (4h) — top bar, 3-pane layout, transcript rendering with partial/final handling, mic capture reuse (existing `dsp.js`/worklet logic ported as-is), alert card list with slide-in, command bar + simulate input.
5. **Cockpit polish — the wow moment** (3h) — offending-phrase underline sync, voice orb amplitude-reactive rendering from `agent_audio`, risk-meter dots, "Spoken verbatim ✓" badge timing. **This task is the one that must not be cut** — it's the entire video payoff.
6. **Report screen** (2h) — score ring count-up, contradiction timeline, clause citations, facts row, export button.

**Total: ~16h.** Cut line if short on time: cut task 6's timeline-hover interaction (static list is fine) and task 2's preview loop (ship a static screenshot-style frame instead) before ever touching task 5 — task 5 is the demo's entire reason for existing.

# ClauseCatcher — UI Judge Critique

Scope: judged from code only (`web/index.html`, `styles.css`, `app.js`) — vanilla HTML/CSS, navy/slate, no framework, no motion library, no build step. Backend/voice pipeline is verified working; this file is about what a judge SEES.

## 1. Judge panel — current UI, 1-10

**Application of Technology judge — 6/10.** The tech (AssemblyAI Streaming STT + Voice Agent + Gemini) is real and hard, but the UI hides it. Status is two grey text pills (`STT: —`, `Voice: —`) — no judge will register that three separate AI systems are running live. There's no visual proof of "streaming" (no waveform, no partial-token flicker beyond italic text). The demo contract button and simulate-input textbox make it look like a toy chat form, not a voice pipeline.

**Presentation judge — 2/10.** No cards, no elevation, no motion, no hierarchy beyond borders. Alerts are `<li>` with a red border and `prepend()` — they just snap into existence, no slide/highlight. The header is a flat navy bar with a two-letter monogram. Every panel is the same white box with the same 6px radius. This reads as an admin CRUD screen, not a "live guardian watching your call."

**Business Value judge — 5/10.** The report screen (`renderReport`) is a plain label/value list — no compliance score, no visual severity, no sense of "this saved you from a bad call." A compliance buyer evaluating this as a product sees a debug panel, not a trust artifact. The contradiction cards in the report reuse the alert card styling verbatim — no differentiation between "live alert" and "audit record."

**Originality judge — 4/10.** The underlying idea (spoken clause enforcement mid-call) is original and the judge will credit that from the pitch — but the screen itself is templated: header/panel/list/button, nothing a judge hasn't seen in 50 other hackathon CRUD apps. Nothing on screen signals "we built something no one else has."

**Average: 4.25/10** — consistent with the user's own 1/10 gut score on first impression; code confirms it's a functional form, not a demo-able product.

## 2. The wow moment for the video

**Moment:** t≈0:XX, rep says the offending line ("we can do a verbal discount for a big client"), ~2s later the contract-alert fires and the Voice Agent speaks the literal clause aloud.

**How the screen must look/move at that exact second** (none of this exists today — `prependAlertCard` just inserts a static `<li>`):
1. The rep's offending phrase in the transcript pane gets a red underline/highlight the instant Gemini flags it (before the voice even starts) — `sentence` is already in `msg`, so highlight the substring in the transcript log, don't just append plain text.
2. A clause card slides in from the right (translateX + opacity, ~250ms ease-out) into the alert stack — not `prepend()`, an actual CSS transition on insert.
3. Inside the card, the literal contract text (`literal_text`) highlights word-by-word in sync with the Voice Agent's speech — this is the single highest-leverage addition: it visually proves the voice output *is* the literal clause, not a paraphrase, which is the whole value prop.
4. A small waveform/equalizer bars next to "ClauseCatcher speaking…" (`agent_audio` chunks already arrive with `pcm16_b64` — drive bar heights off decoded amplitude, cheap canvas draw, no library needed).
5. A timestamp chip and a risk-meter needle (green→red) ticks up on the card, giving judges a number to react to, not just text.

Everything needed to drive this is already in `msg` payloads (`alert` has `section_number, title, literal_text, sentence, t`; `agent_audio` has the raw PCM). This is a rendering problem, not a backend problem.

## 3. Rebuild screen list (what each must say in <3s)

1. **Landing/hero** — "AI listens to your sales calls live and stops reps from promising things the contract doesn't." One CTA: "Watch it catch a lie live" → demo.
2. **Contract setup** — drop a PDF, watch clause cards extract and stack in with a stagger animation (150ms each) — communicates "it actually read your contract," not "we have a hardcoded demo file."
3. **Live call cockpit** — 3-pane: transcript (offending phrase highlightable), clause-risk meter/radar (visual number, not text), alert stack (the wow moment above), agent voice indicator (waveform), ask-a-clause box. Must communicate "this is watching in real time" within 3 seconds of load — a pulsing "LIVE" dot does more than the current grey pill.
4. **Report** — one big compliance score (e.g. "94% clean — 1 contradiction caught"), a horizontal contradiction timeline (dots on a line, not a stacked list), an "export" button (even if it just triggers `window.print()` — the *feel* of exportability matters more than the feature).
5. **"How it works" strip** — three logos/labels in a row: AssemblyAI Streaming STT → Gemini claim check → AssemblyAI Voice Agent, each with a one-line caption. This single strip is what earns Application-of-Technology points — right now nothing on screen names the stack at all.

## 4. What top competitors show vs. what makes ClauseCatcher credible

Polished voice-agent hackathon demos typically lean on: dark glass-morphism dashboards, animated waveforms, particle/gradient backgrounds, big glowing "AI is thinking" spinners — generic AI theater that says "look how slick our frontend dev is," not "trust this system."

ClauseCatcher's buyer is a compliance/sales-ops lead, not a consumer. Generic AI glitter (gradients, particles, glowing orbs) actively hurts credibility for that buyer — it reads as a toy. What reads as credible instead:
- **Precision over motion**: monospace or tabular numerals for section numbers, exact quote blocks with visible quotation marks, no rounded "friendly" AI framing.
- **Evidence-first**: every alert shows the literal clause text right next to what was said — already the right instinct in `prependAlertCard`, just needs visual weight (larger type, clear "contract says" vs "rep said" columns) instead of being buried in a small italic blockquote.
- **Muted, legal-adjacent palette**: the current navy/slate (`#123a5c`) is actually the right direction — keep it, don't chase a purple-gradient SaaS look. Just add depth (subtle shadows, card elevation) instead of flat borders.
- **Calm real-time indicators, not hype**: a small steady pulse for "listening," not a spinning brain icon.

## 5. Top 10 UI must-haves, ranked by judge-impact-per-hour

| # | Item | Judge impact | Hours |
|---|---|---|---|
| 1 | Word-synced clause-text highlight during voice playback (the wow moment) | Very high | 2 |
| 2 | Alert card slide-in animation + highlight offending transcript phrase | Very high | 1.5 |
| 3 | "How it works" strip (STT → Gemini → Voice Agent) on landing/cockpit | High | 1 |
| 4 | Live waveform/bars on agent voice indicator (driven by real `agent_audio` amplitude) | High | 1.5 |
| 5 | Compliance score + contradiction timeline on report screen | High | 2 |
| 6 | Landing/hero screen with one CTA (currently doesn't exist — app opens straight to setup form) | High | 1.5 |
| 7 | Clause extraction stagger animation on contract upload | Medium | 1 |
| 8 | Card elevation/shadow system to replace flat borders everywhere | Medium | 1 |
| 9 | Pulsing "LIVE" indicator replacing grey status pills | Medium | 0.5 |
| 10 | Risk meter/gauge component on cockpit | Medium | 1.5 |

**Total: ~13.5 hours** for the full list; items 1-3 (4.5 hours) alone would move the Presentation score from 2/10 to a defensible 6-7/10 and directly create the video's wow moment. No new dependencies needed — CSS transitions, `<canvas>` for the waveform, and the data already in the existing WS message payloads cover all 10 items.

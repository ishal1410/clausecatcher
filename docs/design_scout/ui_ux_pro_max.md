# ClauseCatcher Cockpit — Design Scout (ui-ux-pro-max)

Scope note: context budget ran out mid-scout. Verified picks below come only from pages actually opened and screenshots actually viewed: **21st.dev** (`/s/voice`, `/s/notification`, `/s/progress`, `/s/dashboard`) and **Magic UI** (`/docs/components/animated-beam`). Aceternity UI, React Bits, and Kokonut UI were queued (Aceternity's `/components` index was screenshotted to disk but not viewed/scored) and not covered — say so rather than fabricate picks from them.

All screenshots: Playwright headless Chromium, 1440x900, ~3s settle, saved under
a local scratch folder `design_scout/uupm/` (not committed).

## Design system baseline (ui-ux-pro-max --design-system)

Query: `"compliance monitoring dashboard dark trustworthy"`

- Style: Glassmorphism (dark-mode supported) — frosted cards, 10-20px backdrop blur, 1px rgba(255,255,255,0.2) borders, layered depth. Fits "trustworthy, high-contrast" brief better than flat/skeuomorphic.
- Colors: background `#0F172A`, card `#1B2336`, foreground `#F8FAFC`, muted `#94A3B8`, accent `#22C55E` (status-green), destructive `#EF4444`, border `#475569`.
- Typography: Fira Code (data/numbers) / Fira Sans (UI text) — "dashboard, data, analytics, technical, precise."
- Anti-patterns to avoid: slow/non-live-feeling updates, emoji-as-icon, low-contrast light-on-light text.

---

## Per-role picks

### 1. Voice visualizer (AI voice agent speaking the clause)
**Page:** https://21st.dev/s/voice — screenshot `21st_voice.png`
**Pick: "Voice Dictator" by ulcapsule** — Score: **9/10**
Glowing white ring on pure black, single focal orb, minimal chrome, caption line below ("Generate expressive prompts by speaking..."). Reads as premium/serious, not toy-like — matches the "trustworthy" brief far better than the colorful gradient "Siri Orb" (playful, multi-blob) also on this page.
Reason to build cockpit's orb on this pattern: ring geometry is trivial to drive off Web Audio `AnalyserNode` amplitude (scale/opacity/blur of the ring), no extra dependency.

**Alt: "Siri Wave" by 40973894** — Score: 7/10 — particle-cluster on black, good for an idle/listening state distinct from the active-speaking ring.

### 2. Pipeline / beam (STT → Gemini → Voice Agent)
**Page:** https://magicui.design/docs/components/animated-beam — screenshot `magicui_home.png`
**Pick: Magic UI "Animated Beam"** — Score: **8/10**
Exactly the shape needed: circular icon nodes with a light beam animating along the connecting path, supports uni-/bi-directional and multiple inputs/outputs (3 sources → 1 hub → outputs, or linear left-to-right). Demo shown is on a light doc background; component is unstyled SVG/CSS underneath so it drops cleanly onto the `#0F172A` cockpit background — swap node icons for AssemblyAI/Gemini/Voice-Agent logos, dark node fill, green "active" beam vs. slate "idle" beam.

### 3. Alert / contradiction card
**Page:** https://21st.dev/s/notification — screenshot `21st_notification.png`
**Pick: "Dismissible Alert Stack" by 7ovr** — Score: **8.5/10**
Vertically stacked cards, each with a left status icon (success/info/warning/error) + bold title + one-line body + dismiss X — directly reusable for "contradiction alert quoting the exact clause": icon = severity, title = the violated clause name, body = the quoted contract text + what was said on the call.

### 4. Live transcript
No dedicated "transcript" component category was queried directly (context ran out before a 5th 21st.dev URL); best verified substitute seen on the same page as the voice picks:
**Page:** https://21st.dev/s/voice — screenshot `21st_voice.png`
**Pick: "Chat Bubble" pattern (by Kavi Katiyar, visible on `/s/voice`)** — Score: **6.5/10, unverified in isolation**
Rounded message bubbles with avatar + timestamp is the right primitive for a scrolling live transcript (rep on one side, prospect on the other, latest line auto-highlighted). Flag this as a weaker pick than the others — it wasn't opened on its own page, only seen as a thumbnail — and re-scout `21st.dev/s/chat` or `/s/transcript` before committing.

### 5. Status of 3 AI systems (AssemblyAI STT / Gemini / AssemblyAI Voice Agent)
**Page:** https://21st.dev/s/dashboard — screenshot `21st_dashboard.png`
**Pick: "System Status Block" by Preet Suthar** — Score: **9/10**
Exactly this use case out of the box: rows labeled API / Database / Auth / Email, each with a pulsing green bar-graph + "Operational"/"Degraded" text + "Last checked" timestamp. Relabel the three rows to AssemblyAI STT / Gemini / Voice Agent; reuse the pulse-bar as a live-activity indicator (bar animates while that system is actively processing audio/text).

### 6. Clause risk meter
**Page:** https://21st.dev/s/progress — screenshot `21st_progress.png`
**Pick: "Circle Progress" by oc tung** — Score: **8/10**
Row of small ring gauges at 0/25/50/75/100% in a green→yellow→red progression — maps directly onto a risk meter (low/medium/high) without inventing a new color scale. Use one ring, color driven by current risk band, percentage = model-confidence-weighted risk score.

### 7. End-of-call report score
**Page:** https://21st.dev/s/progress — screenshot `21st_progress.png`
**Pick: "Progress" (single ring, green, by Sean Hello)** — Score: **7.5/10**
Clean single ring with big centered percentage + label underneath ("43% / Upload Status" → repurpose as "87% / Compliance Score"). Large-number-first hierarchy suits a report's headline metric; pair with Fira Code tabular numerals for the percentage per the typography pick above.

---

## Cockpit composition (wireframe-level, 1280x720)

Background `#0F172A`, glass cards `#1B2336` @ ~85% opacity + 14px blur, border `1px solid rgba(255,255,255,0.08)`, body font Fira Sans, numerals Fira Code.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  ClauseCatcher            ● LIVE CALL 04:12          [System Status strip] │  56px header
├───────────────────────────────┬──────────────────────────────────────────┤
│                                │  RISK METER (Circle Progress ring)        │
│  LIVE TRANSCRIPT               │   62% — MEDIUM                            │
│  (Chat Bubble list, auto-      ├──────────────────────────────────────────┤
│  scroll, rep left / prospect   │  CONTRADICTION ALERT (Dismissible Alert   │
│  right, latest line glow)      │  Stack card, red icon)                    │
│  ~58% width, full height       │  "Rep said: 'guaranteed returns'"         │
│                                │  Clause 4.2: "No guarantee may be implied"│
│                                ├──────────────────────────────────────────┤
│                                │  AI VOICE AGENT                           │
│                                │  (Voice Dictator ring, glowing/pulsing    │
│                                │   on amplitude, black inset panel)        │
│                                │  "Speaking correction now..."             │
├───────────────────────────────┴──────────────────────────────────────────┤
│  PIPELINE STRIP (Animated Beam, horizontal, dark nodes)                    │
│  [AssemblyAI STT] ──beam──▶ [Gemini] ──beam──▶ [Voice Agent]               │
│  each node ring-pulses green when actively processing                     │
└────────────────────────────────────────────────────────────────────────────┘
```

End-of-call report (separate screen, same system): centered "Progress" score ring (large, green, Fira Code numeral) as the headline compliance score, with the risk-meter ring style reused per-clause below it as a scrollable list of flagged moments.

---

## Gaps / next pass
- Aceternity UI, React Bits, Kokonut UI: not opened — context ran out before the second scouting pass. Aceternity's component index was screenshotted (`aceternity_home.png`) but not viewed/scored; treat as unscored, not "no match."
- Transcript pick (#4) is the weakest — it's a thumbnail sighting, not a dedicated page visit. Re-verify against `21st.dev/s/chat` before locking it in.
- 21st.dev component URLs above are catalog-page picks (`/s/<category>`), not yet resolved to individual `https://21st.dev/@author/components/slug` permalinks — resolve before handing to implementation.

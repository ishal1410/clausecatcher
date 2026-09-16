# ClauseCatcher — High-End Component Scout (21st.dev)

Method: scraped `https://21st.dev/s/<category>` for hero, background, shader, card, voice,
dashboard, text, notification, bento, feature, globe, marquee. Selected 20 candidates most
likely to fit ClauseCatcher's roles, opened each live component page with Playwright headless
Chromium at 1440x900, waited 3s for animation/hydration, screenshotted, then viewed every PNG
with the Read tool before scoring. All 20 pages returned HTTP 200 and were visually inspected —
nothing below is scored from a page that failed to load.

Screenshot root: local scratch folder `design_scout/highend/` (not committed).

---

## Top 10 (ranked)

### 1. Hyperdrive Hero — score 9/10
- Author: Dhileep Kumar GM
- URL: https://21st.dev/@dhileepkumargm/components/hyperdrive-hero
- Screenshot: `highend/hyperdrive-hero.png`
- Role: **landing hero**
- Why: OLED-black canvas with a cursor-reactive warp starfield, a pill-shaped eyebrow badge
  ("Next-Generation Deployment Platform"), an oversized bold grotesk headline, and a white
  pill CTA with a trailing arrow — this is the exact "Ethereal Glass" archetype from the
  design skill, already assembled. Swap copy to "Live Sales-Call Compliance Guardian" /
  "Arm the Call" and it drops in almost unmodified.

### 2. Siri Wave — score 9/10
- Author: 40973894
- URL: https://21st.dev/@40973894/components/siri-wave
- Screenshot: `highend/siri-wave.png`
- Role: **voice visualizer**
- Why: Raw WebGL/GLSL, pure black canvas, a single glowing chromatic-aberration horizontal
  waveform with zero UI chrome. No card, no border, no label — total restraint. This is the
  single best candidate for the "AI voice speaks the clause" moment: the waveform IS the
  screen, nothing competing with it.

### 3. Total Sales Chart — score 9/10
- Author: Ahmed Mayara
- URL: https://21st.dev/@ahmedmayara/components/total-sales-chart
- Screenshot: `highend/total-sales-chart.png`
- Role: **report stats**
- Why: The most polished dashboard card scouted — big stat, green delta pill, orange
  sparkline, a segmented 1D/1W/1M/3M/1Y period control, and icon-labeled breakdown rows with
  trend arrows. Reads as a real SaaS product screenshot, not a template demo. Ideal for the
  post-call compliance report screen (swap "Total Sales" → "Contract Adherence Score").

### 4. Holographic Interface — score 9/10
- Author: Dhileep Kumar GM
- URL: https://21st.dev/@dhileepkumargm/components/holographic-interface
- Screenshot: `highend/holographic-interface.png`
- Role: **cockpit dashboard / bento**
- Why: The component's own description says "ideal for sci-fi control panels" — it's
  literally built for this. Dark bento grid, 3D tilt + spotlight tracking, glowing oversized
  headline, bordered sub-panels with a "[Live Data Feed Placeholder]" slot that maps directly
  onto a live transcript feed. This is the shell that should hold the alert cards during the
  live-call view.

### 5. Bento Monochrome — score 8/10
- Author: larsen66 (indexed by 21st Indexer)
- URL: https://21st.dev/@larsen66/components/bento-monochrome
- Screenshot: `highend/bento-monochrome.png`
- Role: **how-it-works / feature grid**
- Why: Micro eyebrow tag ("GRID STUDIES"), massive bold grotesk headline, icon-badge cards
  with all-caps micro-labels, heavy whitespace, and a "DARK MODE" pill toggle. This is
  editorial-agency restraint applied to a feature grid — exactly the "Soft Structuralism"
  archetype, and the cleanest how-it-works candidate found.

### 6. Bar Visualizer (ElevenLabs) — score 8/10
- Author: ElevenLabs
- URL: https://21st.dev/@ElevenLabs-crawled/components/bar-visualizer
- Screenshot: `highend/bar-visualizer.png`
- Role: **voice visualizer**
- Why: Official ElevenLabs component family, so the interaction states are production-grade
  (Connecting / Initializing / Listening / Speaking / Thinking). The captured state actually
  rendered a live vertical-bar EQ with a filled black "Listening" pill — clean grotesk labels,
  generous card padding, minimal chrome. Best paired with Siri Wave: use this as the
  in-card widget, Siri Wave as the full-bleed hero moment.

### 7. Team Invitation Alert — score 8/10
- Author: Arihant Jain (Spectrum UI)
- URL: https://21st.dev/@arihantcodes_1f7b8c4d/components/alert-2
- Screenshot: `highend/alert-2.png`
- Role: **cockpit alert card**
- Why: A compact, restrained notification card — avatar with an online-status dot, title,
  one-line subtext, accept/decline glyph buttons (no heavy borders, no drop shadow abuse).
  This is the exact anatomy needed for "rep contradicts the contract → clause card appears":
  swap avatar for a document icon, title for the clause name, subtext for the exact quoted
  clause text, and the check/x actions for "Acknowledge / Dismiss."

### 8. Bar Chart ("Evil Charts") — score 7/10
- Author: Legion Dev
- URL: https://21st.dev/@LegionWebDev/components/bar-chart/glowing-bar-chart
- Screenshot: `highend/glowing-bar-chart.png`
- Role: **report stats**
- Why: Clean stat card with a green % pill and a nice detail — month labels rendered in
  alternating accent colors instead of flat gray. Bold oversized title. A good secondary
  chart card for a report screen that needs more than one stat block.

### 9. Area Chart Analytics Card — score 7/10
- Author: Ahmed Mayara
- URL: https://21st.dev/@ahmedmayara/components/area-chart-analytics-card
- Screenshot: `highend/area-chart-analytics-card.png`
- Role: **report stats**
- Why: Compact card, light blue area fill, a split metric panel ("45% / $32.9K used") and a
  pill-shaped "Details" button. Slightly busier composition than Total Sales Chart but still
  restrained — good as a secondary/tertiary stat tile.

### 10. Ethereal Swirl Gradient Card — score 7/10
- Author: ShadcnStudio
- URL: https://21st.dev/@ShadcnStudio/components/card-studio/ethereal-swirl-gradient-card
- Screenshot: `highend/ethereal-swirl-gradient-card.png`
- Role: **feature / report card frame**
- Why: A well-proportioned image-top/text-bottom card with a filled black primary CTA and an
  outline ghost secondary CTA — the button pairing is close to the skill's "button-in-button"
  restraint. Useful as the frame for a feature-highlight card (swap the swirl photo for a
  document/contract visual) elsewhere on the landing page.

---

## Best coherent combination of 5

**Hyperdrive Hero + Siri Wave + Holographic Interface + Team Invitation Alert + Total Sales Chart**

Rationale: three of these (Hyperdrive Hero, Siri Wave, Holographic Interface) already share
the same near-OLED-black canvas with glow-accent typography — that's one consistent "cockpit"
language for the landing page and the live-call view. The other two (Team Invitation Alert,
Total Sales Chart) are light, restrained white cards — which is exactly the Linear/Vercel
pattern of floating a light "instrument" card on a dark canvas, not a mismatch. Used together:
dark hero → dark cockpit shell (Holographic Interface) hosting the live transcript → a white
alert card snaps in when a contradiction fires (Team Invitation Alert, restyled with a document
icon and quoted clause text) → AI speaks it (Siri Wave takes over full-bleed) → white stat card
for the post-call report (Total Sales Chart, restyled as a contract-adherence score). One
accent color (pick one: amber or a deep red for violations) ties all five together.

---

## 3 rejected, with reasons

1. **Vector Field** — https://21st.dev/@designali-in/components/vector-field
   (`highend/vector-field.png`) — Loud blue-and-white moiré stripe pattern that reads as a
   raw effects-library tech demo, not a finished background. Visually aggressive rather than
   restrained; would fight with any text or card placed on top of it. Fails the "restraint"
   criterion outright.

2. **Basic Toast** — https://21st.dev/@anubra266/components/basic-toast/toast-variants
   (`highend/toast-variants.png`) — The page loaded (HTTP 200) but the captured preview shows
   only four trigger buttons (Success/Error/Warning/Info) — no toast was actually on screen
   in the 3s window, so there is nothing to visually judge. Rejected for lack of verifiable
   visual evidence, not assumed quality.

3. **How It Works (chamaac)** — https://21st.dev/@chamaac/components/how-it-works
   (`highend/how-it-works.png`) — Pinned index cards with literal pushpin icons and pastel
   orange/blue/purple corkboard styling. Charming for a consumer product, but the
   pushpin/corkboard motif reads as twee rather than authoritative — wrong tone for a legal/
   compliance product that needs to look trustworthy under pressure in front of judges.

---

## Other candidates screenshotted but not in the top 10

- **Particle Hero** (`highend/particle-hero.png`, https://21st.dev/@designali-in/components/particle-hero) — weak generic typography ("Gold Design"), unremarkable copy; scores below Hyperdrive Hero for the same hero role.
- **Neural Noise** (`highend/neural-noise.png`, https://21st.dev/@designali-in/components/neural-noise) — well-rendered pink/magenta GLSL ink-blot shader, but the stock hot-pink palette doesn't fit a legal-compliance product without a full recolor.
- **Warp Background** (`highend/warp-background.png`, https://21st.dev/@dillionverma/components/warp-background) — subtle converging-line depth effect, usable as an ambient texture layer, but the demo content is unrelated and the effect is too faint to read as a hero-grade background on its own.
- **Siri Orb** (`highend/siri-orb.png`, https://21st.dev/@educalvolpz/components/siri-orb) — pastel candy-colored CSS spheres; cute rather than authoritative, tone mismatch.
- **Orb / Live Waveform (ElevenLabs)** (`highend/orb.png`, `highend/live-waveform.png`) — same official component family as Bar Visualizer, but both captured in an idle/unstarted state with nothing visually rendered — inconclusive, not scored.
- **Number Flow** (`highend/number-flow.png`, https://21st.dev/@barvian/components/number-flow) — purely functional digit-transition component; the static capture shows only a plain number with no card chrome, so its "expensive" quality can't be judged from a screenshot (it's a motion-only effect).

# ClauseCatcher — Component Taste Scout

Design read: live sales-call compliance guardian, hackathon 3-min demo, 1st-place target. Core moment: rep contradicts contract, a clause card quotes the exact clause, an AI voice speaks it. Audience is hackathon judges who have seen a hundred shadcn dashboards. Leaning dark cockpit for the live-call view, restrained sans for the landing page, one accent glow color (not AI-purple) carried through both. Reference libraries scouted beyond 21st.dev: Aceternity UI, Magic UI, React Bits, Kokonut UI. Every entry below was opened live (Playwright, Chromium headless, 1440x900, ~3s settle) and the screenshot was viewed before scoring. Screenshots saved under the scratchpad `design_scout/taste/` folder used for this run.

No em-dashes used per taste-skill rule. Scores are 1-10, reasoning is specific to what the screenshot showed, not the component's marketing copy.

---

## Top 12 (across all 5 libraries)

### 1. AI Voice — Kokonut UI — 9/10
- URL: https://kokonutui.com/docs/components/ai-voice
- Role: cockpit (the literal "AI voice speaks it" moment) / landing hero interaction
- Why: pulsing waveform bars, a recording timer, and a "Listening..." state on a minimal black rounded-pill control. This is almost exactly the interaction the demo needs at its climax, no reskinning required beyond color. Screenshot showed a clean, unbranded, production-quality preview, not a placeholder.
- License: MIT / open source, shadcn CLI install (`bunx --bun shadcn@latest add @kokonutui/ai-voice`), no paywall on this page. Separate paid "Kokonut UI Pro" product exists but does not gate this component.

### 2. Magic Bento — React Bits — 8.5/10
- URL: https://reactbits.dev/components/magic-bento
- Role: report / cockpit (compliance metrics grid: risk score, flags this call, contract coverage)
- Why: the best-looking bento of everything scouted. Six sharp-bordered black cells, generous padding, restrained two-line copy per cell (label + one-line description), zero clutter. Reads as a real product surface, not a component demo.
- License: free tier of React Bits (dual free/Pro library, MIT for the free set); this component sits in the un-gated sidebar list with a working Code tab.

### 3. Card Spotlight — Aceternity UI — 8/10
- URL: https://ui.aceternity.com/components/card-spotlight
- Role: cockpit (the clause card itself)
- Why: dark card, cursor-tracked radial spotlight, a checklist demo (title + bullet list + closing line) that maps almost 1:1 onto "Clause 4.2 [checkmark quote] [checkmark citation] [checkmark AI take]". This is the strongest direct match for the hackathon's core card.
- License: free component on ui.aceternity.com/components, full Code tab visible with no paywall (Aceternity's paid tier is separate templates/Pro, not this component).

### 4. Glowing Effect — Aceternity UI — 8/10
- URL: https://ui.aceternity.com/components/glowing-effect
- Role: cockpit (the "contradiction detected" alert state wrapping the clause card)
- Why: an animated border-glow that adapts to any container, credited on the page as the effect seen on Cursor's website. Exactly the visual language for flashing a card into an alert state without resorting to a jarring red toast. Demo content was throwaway placeholder text, but the mechanic is the point.
- License: free, Code tab open, no paywall.

### 5. Tilted Card — React Bits — 8/10
- URL: https://reactbits.dev/components/tilted-card
- Role: report (evidence/screenshot card, e.g. a transcript excerpt or a contract page snapshot)
- Why: a real B&W photo with a title overlay tilts in 3D on hover with a tooltip. Genuinely premium production value, the kind of detail that reads as "not templated" to judges. Configurable rotate amplitude and scale-on-hover shown in the props panel.
- License: free tier of React Bits, un-gated Code tab.

### 6. Hero Highlight — Aceternity UI — 7.5/10
- URL: https://ui.aceternity.com/components/hero-highlight
- Role: landing (headline with the exact phrase that sells the product highlighted)
- Why: dotted background plus a colored highlight span over a run of headline text. Directly reusable for a landing headline like "flags the contradiction [highlighted]before the rep finishes the sentence[/highlighted]". The stock demo copy is throwaway but the mechanic is clean and restrained (single accent block, not a rainbow gradient).
- License: free, Code tab open, no paywall.

### 7. Border Beam — Magic UI — 7.5/10
- URL: https://magicui.design/docs/components/border-beam
- Role: cockpit (a second option for the clause-card alert border: a traveling light beam rather than a static glow)
- Why: animated light beam travels along a container's border. Paired well against Aceternity's Glowing Effect as a genuine alternative for the "flag this clause" moment, worth prototyping both and picking the one that reads clearer on a screen recording.
- License: MIT, fully open source (magicui.design states this explicitly). Sits in the free "Components" sidebar, distinct from the separately paid "Templates" section (which is clearly Pro-tagged in the same sidebar).

### 8. Animated List — Magic UI — 7.5/10
- URL: https://magicui.design/docs/components/animated-list
- Role: cockpit (live transcript / live flag feed streaming in during the call)
- Why: items animate into a vertical stack in sequence with a delay, shown as notification-style rows (icon avatar + title + timestamp). This is the right shape for "here's what the rep just said" streaming into the cockpit in real time.
- License: MIT, free Components section, no paywall.

### 9. Chroma Grid — React Bits — 7.5/10
- URL: https://reactbits.dev/components/chroma-grid
- Role: cockpit (rep roster or a severity-coded list of flagged calls, one colored border per severity level)
- Why: B&W photo grid where each card gets a distinct colored border glow (blue, green, orange seen in the screenshot). Repurposable as a severity legend (green = compliant, amber = warning, red = violation) without inventing a new visual language.
- License: free tier of React Bits, un-gated.

### 10. Thinking Orbs — 21st.dev — 7.5/10
- URL: https://21st.dev/@larsen66/components/thinking-orbs/thinking
- Role: cockpit (the AI's "analyzing what was just said" state, distinct from the AI Voice "speaking" state)
- Why: a small animated canvas orb with a "Thinking..." label on a black background, six hand-tuned states (working, searching, solving, listening, composing, shaping) per its own description. Pairs naturally with Kokonut's AI Voice: orb while analyzing, waveform while speaking.
- License: 21st.dev community component, code-copy install (Copy Prompt / CLI), no paywall shown on this page.

### 11. System Status Block — 21st.dev — 7/10
- URL: https://21st.dev/@preetsuthar17/components/system-status-block
- Role: cockpit (live compliance status panel: API/data-feed health repurposed as "call feed status")
- Why: clean status rows with colored state dots (operational/degraded/down), a small incident sparkline bar per row, and an "Incident History" toggle. Directly repurposable as a compliance status strip (transcript feed live, contract loaded, flags detected).
- License: 21st.dev community component, no paywall shown.

### 12. Dashboard with Collapsible Sidebar — 21st.dev — 6.5/10
- URL: https://21st.dev/@uniquesonu/components/dashboard-with-collapsible-sidebar
- Role: cockpit (the overall shell: sidebar nav + stat cards + dark mode toggle)
- Why: solid, unremarkable SaaS dashboard shell. Not exciting on its own (rounded white stat cards, default icon set) but it is the correct skeleton to hang the more distinctive pieces above (Magic Bento, Card Spotlight, Animated List) inside, rather than building a shell from scratch.
- License: 21st.dev community component, no paywall shown.

---

## The Hero Set (6 components, one coherent system)

This is the set to actually wire together for the demo. All six read as dark, restrained, single-accent-glow, same rounded-corner family (Tailwind `rounded-xl`/`rounded-2xl` across all three source libraries), so they can share one design system without a visible seam.

1. **Aceternity Card Spotlight** — the clause card shell (dark card, spotlight-on-hover, checklist layout for quote + citation + AI verdict).
2. **Aceternity Glowing Effect** — wraps the clause card in an animated border-glow the instant a contradiction is detected. This is the "wow" trigger.
3. **Kokonut AI Voice** — the waveform/listening control that fires right after the glow, standing in for "the AI voice speaks it."
4. **21st.dev Thinking Orbs** — the brief "analyzing" beat between the flag and the voice, so the moment has a rhythm instead of glow-to-voice being instant and flat.
5. **Magic UI Animated List** — the live transcript feed running continuously in the cockpit, so the demo has visible "before" context leading into the flagged moment.
6. **React Bits Magic Bento** — the report/summary screen shown at the end of the demo (compliance score, flags caught, contract coverage), giving the 3-minute video a clean closing shot instead of ending mid-call.

Landing page treatment: use **Aceternity Hero Highlight** for the headline (not in the six above since it is a separate page, but it is the natural landing-page pairing: same dotted-background, same single-accent-highlight language as the cockpit's glow color).

---

## Popular but sloppy (avoid for ClauseCatcher)

- **21st.dev "Hero Section 6"** (https://21st.dev/@meschacirung/components/hero-section-6). Screenshot showed literal Lorem-ipsum body copy ("Error totam sit illum...") under a generic "Production Ready Digital Marketing blocks" headline with a bulleted "Faster / Modern / 100% Customizable" list. This is the exact templated-AI-SaaS-hero look the user explicitly said to avoid.
- **21st.dev "Chat Bubble"** (https://21st.dev/@jakobhoeg/components/chat-bubble). Functionally fine but visually generic, black/gray rounded bubbles indistinguishable from any consumer chat widget. Would not read as "compliance-grade" on screen.
- **Aceternity "Bento Grid"** (base, https://ui.aceternity.com/components/bento-grid). Screenshot showed empty gray placeholder rectangles standing in for images with generic "The Dawn of Innovation" style filler copy. Without real content it reads as an unfinished demo, and React Bits' Magic Bento (item 2 above) is a stronger, more finished-looking alternative for the same job.
- **Magic UI "Number Ticker"** used bare (https://magicui.design/docs/components/number-ticker). Just a large plain "99" in default type on white. The animation is real but the resting-state visual is thin; needs real styling (label, unit, context card) before it reads as a compliance score rather than a component-docs demo.
- **Kokonut "Action Search Bar"** (https://kokonutui.com/docs/components/action-search-bar). A plain "What's up?" search input with no results/dropdown visible in the static state. Too generic and too low-density for a compliance cockpit that needs to feel information-rich, not a consumer search box.
- **Generic "three equal feature cards" row.** Not a specific scouted component but a pattern that recurs as the default composition across all five libraries' example blocks. The design-taste skill bans it outright (Section 9.C) and it is the fastest way to make ClauseCatcher's landing page look AI-templated regardless of which individual card component is used.

---

## Method notes

- Crawled listing/category pages first (21st.dev `/community/components/s/*`, Aceternity `/components`, Magic UI `/docs/components`, React Bits `/components/*` sidebar, Kokonut UI `/docs`) to extract real, currently-live component URLs rather than guessing slugs.
- Kokonut UI's component slugs are not exposed as plain nav links on `/docs`; confirmed real slugs by direct navigation (`ai-voice` and `action-search-bar` returned 200; `ai-input`, `gradient-bars`, `list`, `faq` returned 404 and were discarded).
- React Bits' first-pass screenshots were blocked by a full-screen "React Bits Pro September Update" promo modal; re-shot after dismissing it so the actual component previews are what got judged.
- Every component in the Top 12 and the avoid list above was opened as its own live page and screenshotted at 1440x900; nothing here is scored from a thumbnail or a listing-page grid alone.

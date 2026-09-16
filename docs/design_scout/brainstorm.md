# ClauseCatcher — Visual Design Brainstorm

Non-interactive brainstorm (superpowers:brainstorming, decisions made on the user's behalf per task instructions). Goal: 3 bold, award-caliber visual directions for the landing page + live-call cockpit, each backed by real 21st.dev components that were opened, screenshotted (Playwright, Chromium, 1440x900, ~3-5s settle), and visually judged. Every component listed below returned HTTP 200, had no "not found" body text, and its screenshot was viewed with the Read tool before inclusion. Screenshots were saved to a local scratch folder (`design_scout/brainstorm/`, not committed).

Rejected candidates (opened, viewed, judged generic/off-tone) are noted inline so the trail is honest — components were not cherry-picked after the fact.

---

## Concept 1 — Cinematic Dark Mission Control

**Mood:** A darkened ops room the moment the call goes live. Charcoal-navy panels, hairline grid texture, a single accent color doing all the emotional work (amber/orange for "attention," green for "clear"), monospace micro-labels next to humanist headline type, everything gently backlit like a spotlight is on the rep. The feeling is "NASA console meets fintech risk dashboard" — serious, high-stakes, built for someone whose job depends on catching the mistake before it's said.

**Components:**

1. **Builder OS Bento** — `@drewsephski` — https://21st.dev/@drewsephski/components/builder-os-bento — screenshot: `c1_builder-os-bento.png` — Role: the live-call cockpit's dashboard shell. Why premium: dense charcoal bento grid with a live sparkline, a circular progress ring ("99.8% online"), a scrolling mono-font event log, and a "shipping live" pulse badge — this is the strongest single find of the whole search and maps almost 1:1 onto "call risk score + live transcript log + clause-hit feed."
2. **Chrono Board** — `@dhileepkumargm` — https://21st.dev/@dhileepkumargm/components/chrono-board — screenshot: `c1_chrono-board.png` — Role: the compliance-event timeline panel (contradiction flags with timestamps and status pills). Why premium: deep navy card, soft-glow status dots, colored pill badges (Completed/In Progress) — reads instantly as "live operational feed," not a generic list.
3. **Blueprint Gradient Mesh** — `@larsen66` — https://21st.dev/@larsen66/components/blueprint-gradient-mesh — screenshot: `c1_blueprint-gradient-mesh.png` — Role: base background layer for hero and cockpit. Why premium: deep navy grid with real film-grain noise and a soft vignette — avoids the flat-black-with-glow cliché most dark SaaS hero sections fall into.
4. **Volumetric Studio** — `@alexperezcedeno` — https://21st.dev/@alexperezcedeno/components/volumetric-studio — screenshot: `c2_volumetric-studio.png` — Role: landing hero centerpiece. Why premium: physically-accurate WebGL spotlight rig over a black stage with a bold headline ("Design in a new dimension") — reframe as three spotlights literally "putting the call under scrutiny." Genuinely cinematic, not a stock gradient blob.
5. **Incident Status Timeline** — `@cnippet-dev` — https://21st.dev/@cnippet-dev/components/incident-status-timeline — screenshot: `c1_incident-status-timeline.png` — Role: pattern reference for the "clause violation" status card (investigating → identified → monitoring, colored badges). Ships light-mode by default; needs a dark reskin to match the rest of the cockpit, but the interaction pattern (collapsible timeline, colored status badges, "next update in") is exactly the shape ClauseCatcher needs for a flagged-clause card.

**Rejected in this search (opened, viewed, discarded):** Terminal Bento Grid (`@dhileepkumargm`, screenshot `c1_terminal-bento-grid.png`) — green-phosphor CRT terminal look, too retro/hacker for a compliance product aimed at sales leadership. Glowing Bar Chart and Radar Chart (`@LegionWebDev`, `@intentui`) — both rendered as small, light-mode, generic shadcn charts in their default preview state, no glow visible, no premium feel.

**Judge-appeal score: 8/10.** Communicates "Application of Technology" instantly (live monitoring, real-time), but dark cockpit UIs are the most common visual cliché among AI-agent hackathon submissions in 2026 — strong execution, average novelty.

---

## Concept 2 — Editorial Legal-Luxury

**Mood:** A page that feels like it was designed by a law firm's brand agency, not a dev tool. Warm cream/paper background, oversized serif or high-contrast display type doing the heavy lifting, a single ink-black or deep-burgundy accent, generous whitespace, and one hero visual that is genuinely a magazine spread rather than a SaaS template. The core "gotcha" moment — the clause card — becomes a literal marked-up legal document: text physically highlighted the instant the rep contradicts it.

**Components:**

1. **Minimalist Hero Fashion** — `@kokonutd` — https://21st.dev/@kokonutd/components/hero-fashion — screenshot: `c2_hero-fashion.png` — Role: landing page hero layout. Why premium: real editorial-magazine composition — oversized wordmark, a vertical list of small-caps labels, a "SUMMER 2025"-style season/version caption, and a portrait photo, all on cream. Reskin the wordmark to "ClauseCatcher," the category list to "Live Detection / Instant Alerts / Voice Confirmation," the photo to a call-transcript mockup, and you have a hero no other hackathon team will have.
2. **Text Highlighter** — `@danielpetho` — https://21st.dev/@danielpetho/components/text-highlighter — screenshot: `c2_text-highlighter.png` — Role: the core "contradiction" moment, literally. Why premium: an animated marker-style highlight sweeps behind inline text on hover/scroll/ref-trigger — this is not a metaphor for what ClauseCatcher does, it IS what ClauseCatcher does (highlight the exact clause the rep just contradicted). Single best functional-to-visual match in the entire search.
3. **Text Rotate / Quote Card** — `@danielpetho` — https://21st.dev/@danielpetho/components/text-rotate/quote-card — screenshot: `c2_quote-card.png` — Role: the clause-quote card that pops up during the call. Why premium: large pull-quote typography, a colored dot divider, and a clean attribution line below — exactly the shape needed for "Section 4.2(b): ..." with an attribution of the actual contract clause.
4. **Text Reveal (character-scale)** — `@cnippet-dev` — https://21st.dev/@cnippet-dev/components/text-reveal/character-scale — screenshot: `c2_text-reveal-character-scale.png` — Role: headline entrance animation on the landing page. Why premium: smooth staggered character/word reveal, understated rather than flashy — fits the restrained editorial mood better than a typewriter or glitch effect would.
5. **Paper Texture (Paper Shaders)** — `@paper-design` — https://21st.dev/@paper-design/components/paper-texture — screenshot: `c2_paper-texture.png` — Role: background texture/hero backdrop. Why premium: a genuine animated WebGL shader with real paper-grain noise and a customizable 4-color palette (ships as blue/cream but trivially recolored to cream/ink/burgundy) — gives the "legal document" feel real production value instead of a flat CSS background.

**Rejected in this search (opened, viewed, discarded):** Sakura Editorial Poster (`@httpsdesign-layercomja`, screenshot `c2_sakura-editorial-poster.png`) — cherry blossoms, completely wrong theme despite the promising name. Minimalist Hero (`@ravikatiyar162`, screenshot `c2_minimalist-hero.png`) — well-crafted "less is more" hero but a bright yellow circle + playful tone reads as consumer fashion, not legal/compliance. Reshaped Alert and Meeting Notes Card (`@reshaped`, `@ShadcnStudio`) — both flat, default-shadcn-looking, no visual craft in their default state.

**Judge-appeal score: 9/10.** Highest originality of the three — no other voice-AI hackathon submission is likely to look like a legal magazine spread — and it directly reinforces "Business Value" (a compliance tool that looks trustworthy and premium sells itself to a sales-ops buyer). Slight build risk: the component pool for this direction was thinner than the other two (more rejects per keeper), meaning more custom typography/layout work rather than drop-in components.

---

## Concept 3 — Holographic Voice-First

**Mood:** The call itself is the interface. A glowing, breathing orb sits at the center of the screen and IS the voice agent — it pulses when listening, spins faster when it catches a contradiction, and flares when it speaks the correction aloud. Deep space-black background, soft multi-color conic gradients, frosted-glass panels floating above a barely-visible waveform. Feels like Siri/visionOS crossed with a trading floor.

**Components:**

1. **Orb (Agent Orbs)** — `@ElevenLabs-crawled` — https://21st.dev/@ElevenLabs-crawled/components/orb — screenshot: `c3_elevenlabs-orb.png` — Role: the primary voice-agent state indicator (Idle / Listening / Talking). Why premium: pulled from a real voice-AI company's own design system, three orbs each with distinct conic-gradient colorways and explicit named states — exactly the state machine ClauseCatcher's voice agent needs to visualize.
2. **Live Waveform** — `@ElevenLabs-crawled` — https://21st.dev/@ElevenLabs-crawled/components/live-waveform — screenshot: `c3_elevenlabs-live-waveform.png` — Role: real-time mic input visualizer under the transcript. Why premium: same design-system pedigree as the orb, with explicit "Start Listening / Start Processing / Mode: Static" controls that map directly onto ClauseCatcher's call states. (Note: waveform itself is audio-reactive and renders empty at rest in a static screenshot — visual payoff requires a live mic feed, which the actual product has.)
3. **Siri Orb** — `@educalvolpz` — https://21st.dev/@educalvolpz/components/siri-orb — screenshot: `c3_siri-orb.png` — Role: alternate/backup hero orb, or the "speaking" state specifically. Why premium: genuinely beautiful pure-CSS conic-gradient orb with smooth rotation and three size variants — the single most polished visual asset found in this whole search.
4. **Liquid Glass** — `@suraj-xd` — https://21st.dev/@suraj-xd/components/liquid-glass — screenshot: `c3_liquid-glass.png` — Role: the floating command bar / voice-input pill. Why premium: real frosted macOS-dock-style glass distortion over a rippling background, with a glass pill input ("How can I help you today?") that becomes ClauseCatcher's live status bar.
5. **Aurora Voice Hero** — `@dhileepkumargm` — https://21st.dev/@dhileepkumargm/components/aurora-voice-hero — screenshot: `c3_aurora-voice-hero.png` — Role: full-bleed landing hero background. Why premium: canvas-rendered simplex-noise ribbon lines in purple/cyan that visually read as an audio waveform stretched into an aurora — literally named for this use case.

**Rejected in this search (opened, viewed, discarded):** AI Voice Input (`@kokonutd`, screenshot `c3_ai-voice-input.png`) — functionally on-topic (mic icon, recording timer) but visually inert at rest, no craft in the idle state. Holographic Wall (`@moumensoliman`, screenshot `c3_holographic-wall.png`) — cursor-reactive Pharaonic hieroglyph effect; rendered fully black in a static screenshot and the theme (hieroglyphs) is irrelevant to the product anyway.

**Judge-appeal score: 8/10.** The orb is genuinely gorgeous and technically on-theme for "voice agent," but by 2026 the glowing-orb-as-voice-AI-avatar has become the default visual cliché for this exact hackathon category (it's literally ElevenLabs' own pattern) — judges have likely seen several orbs already this cycle. Strong craft, average novelty for this specific competition.

---

## Recommendation

**Concept 2 — Editorial Legal-Luxury** is the recommended direction, for three reasons specific to this brief:

1. **Originality relative to the competition.** Every other Voice Agent Hackathon entrant is reaching for dark cockpits and glowing orbs (Concepts 1 and 3 both scored 8/10 precisely because they're well-executed versions of the expected look). A cream/serif legal-magazine aesthetic for a *compliance* tool is a genuinely unclaimed lane, and it scored highest (9/10) for exactly that reason.
2. **The core demo moment gets a literal, not metaphorical, visual.** Text Highlighter (`@danielpetho`) doesn't represent "catching a contradiction" — it performs the identical interaction (a highlight sweeping behind the exact clause text) that the judged 3-minute video needs to show. That is a stronger "Application of Technology" beat than a dashboard panel lighting up.
3. **Business Value fit.** ClauseCatcher sells trust to sales-ops and legal buyers. A premium, editorial, almost print-quality interface signals "this is a serious compliance instrument," where a dark hacker-terminal or a glowing sci-fi orb signals "AI toy."

**Build note:** pull the Concept 3 orb/waveform pairing (`@ElevenLabs-crawled/orb` + `@ElevenLabs-crawled/live-waveform`) into the Concept 2 cockpit screen specifically as the live-listening indicator inside a cream/glass panel — small dose of "the AI is alive" energy without abandoning the editorial identity for the whole product. Do not import Concept 1's dark bento shell wholesale; if a denser data view is needed later, borrow only the sparkline/progress-ring pattern from Builder OS Bento and re-skin it in the cream palette.

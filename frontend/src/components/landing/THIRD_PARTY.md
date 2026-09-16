# Landing — third-party design sources

`Landing.tsx` re-implements the visual *patterns* of the components below from
scratch (no source code copied from any site or repo). Listed per the design
scout's picks (`docs/design_scout/high_end.md`, `docs/design_scout/taste.md`)
and the task brief. 21st.dev was intentionally not used or referenced —
several of its components sit behind a paid tier and the task is $0.

| Pattern used | Inspiration | Source URL | License (per design scout) | What we built |
|---|---|---|---|---|
| Voice waveform bars | Kokonut UI "AI Voice" | https://kokonutui.com/docs/components/ai-voice | MIT / open source, no paywall on this component | `VoiceBars` — 5 CSS/`motion` bars animating height, staggered, looping only while `speaking`, static under reduced motion |
| Clause-card spotlight/glow | Aceternity UI "Card Spotlight" + "Glowing Effect" | https://ui.aceternity.com/components/card-spotlight , https://ui.aceternity.com/components/glowing-effect | Free component, Code tab open, no paywall (Aceternity's paid tier is separate templates) | The alert card in `CockpitPreview` uses the shared `components/ui/Card.tsx` `glow="risk-high"` prop (a border-glow ring per `docs/DESIGN_SYSTEM.md` §4), the same primitive the real cockpit's `AlertCard.tsx` uses — chosen over a bespoke layer so the landing preview and the live cockpit read as one system, not two |
| Card spotlight (pointer-tracked) | Aceternity UI "Card Spotlight" | https://ui.aceternity.com/components/card-spotlight | Free component, no paywall | `SpotlightCard` — radial gradient positioned by `useMotionTemplate` motion values, so pointer moves never re-render; used on the hero preview and bento cards |
| Scroll-scrubbed word reveal | Common pattern (e.g. Magic UI "Text Reveal") | https://magicui.design/docs/components/text-reveal | MIT | `ProblemStatement` — per-word opacity from `useScroll` + `useTransform`; plain text under reduced motion |
| Node-to-node connector | Magic UI "Animated Beam" | https://magicui.design/docs/components/animated-beam | MIT, explicitly open source (stated on the site) | `HowItWorks` — a static hairline plus a gradient sweep that lights each of the three pipeline nodes in turn, `motion`-driven, disabled under reduced motion |

No source code was copied from any of the above — each pattern was re-implemented from a description of the interaction, using this project's own `motion/react` + Tailwind setup.

## Fonts / icons

- `@fontsource-variable/inter`, `@fontsource/manrope` (600/700), `@fontsource/jetbrains-mono` — all already wired into `src/index.css` by the shell agent as `font-sans` / `font-display` / `font-mono`. This component uses those Tailwind utilities directly (no local font declarations).
- `lucide-react` — bento icons and the CTA arrow, at 1.5 stroke width. `docs/UI_SCREENS_SPEC.md` calls for Phosphor Light, but `lucide-react` is the icon dependency actually installed for this stack per the task brief.

No AssemblyAI or Gemini calls are made anywhere in this component — the cockpit preview is a scripted, client-side-only animation loop.

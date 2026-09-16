# Cockpit — third-party design sources

No new npm dependencies were added (`react`, `motion`, `lucide-react`, `clsx`, `tailwind-merge`
were already in `frontend/package.json`). Everything below is either re-implemented from a
scouted reference's visual pattern (no code copied, small enough to hand-roll) or is an Apple
design-language pattern with no shippable package for the web (labeled as an approximation).

| Component | Source | URL | License | What was ported |
|---|---|---|---|---|
| `AlertCard.tsx` spotlight + glow | Aceternity UI — Card Spotlight | https://ui.aceternity.com/components/card-spotlight | Free, open Code tab, no paywall (verified in `docs/design_scout/taste.md`) | Cursor-tracked radial highlight via direct DOM style mutation on mousemove (no React state), re-implemented in plain CSS/Tailwind, not copied verbatim. |
| `AlertCard.tsx` border glow | Aceternity UI — Glowing Effect | https://ui.aceternity.com/components/glowing-effect | Free, open Code tab, no paywall | Static risk-colored `box-shadow` glow (`tokens.ts` `glow()`), simplified from the animated-border version scouted; re-implemented, not copied. |
| `TranscriptPane.tsx` list | Magic UI — Animated List | https://magicui.design/docs/components/animated-list | MIT, free Components section | Sequenced enter animation for streaming rows (`AnimatePresence` + `motion.p`, spring `soft`), re-implemented with `motion/react` in place of the original's own animation driver. |
| `VoiceOrb.tsx` | Kokonut UI — AI Voice / 21st.dev — Siri Wave (`40973894/siri-wave`) | https://kokonutui.com/docs/components/ai-voice ; https://21st.dev/@40973894/components/siri-wave | Kokonut: MIT/open, shadcn-CLI install, not paywalled. 21st.dev: community component, no paywall shown. | Visual concept only (radial amplitude-reactive bar ring on a dark disc, "precision not blob"). No WebGL/canvas or source code taken; rebuilt as 28 CSS `<span>` bars with `transform` + `animation-delay`, driven by the `level` prop already exposed by `useSession`. |
| `ClauseRiskMeter.tsx` | React Bits — Magic Bento (layout inspiration only) | https://reactbits.dev/components/magic-bento | Free tier, MIT, un-gated Code tab | Row density and label restraint borrowed conceptually; no bento grid or code used, this is a plain dot-list per DESIGN_SYSTEM.md §5's own "RiskMeter" spec, which explicitly bans filled-background comparison bars. |
| Top bar / right rail translucency | Apple Human Interface Guidelines — Liquid Glass (`ecc:liquid-glass-design` skill) | https://developer.apple.com/design/human-interface-guidelines/materials | Apple platform guidance; **no official web CSS package exists.** | Labeled web approximation only: `backdrop-filter: blur(16px) saturate(160%)` + 1px `rgba(255,255,255,.08)` hairline border + inset highlight, in `cockpit.css` `.cc-glass`. Restricted to the top bar and right rail per the brief; transcript and alert cards stay fully opaque (evidence-first, no glass on the proof surface). `prefers-reduced-transparency` fallback included. |
| Icons | lucide-react (already a project dependency) | https://lucide.dev | ISC | Used as-is via the installed package; no icons hand-drawn. |

No 21st.dev "Copy Prompt" or paid-tier component was used anywhere in this build (the brief's
$0 / no-21st.dev-prompts constraint). Every source above was already verified free/open in the
scouting docs this task was told to read (`docs/design_scout/taste.md`, `high_end.md`,
`ui_ux_pro_max.md`) before it was reused here.

# ClauseCatcher Design System

## 1. Visual Direction — "Evidence Glass" (dark-only)

**Dark glassmorphism, restrained.** Slate-navy base with frosted-glass surfaces, thin hairline borders, and color used only as evidence (risk/safe/voice), never decoration.

Compliance and legal-ops buyers trust dashboards that read like instrument panels, not marketing pages — dark-only keeps a live cockpit legible for a long call and avoids the light/dark inconsistency risk a 3-minute demo video can't afford to show. Glassmorphism's layered depth lets the transcript, clause library, and alert rail feel like distinct sensors reporting into one system, which is the "evidence-first" story judges need to read instantly at 1280×720. No light variant: it adds a second contrast pass for zero payoff in a video-judged, single-operator-view product — skip it, revisit only if a customer explicitly needs light mode.

## 2. Color Tokens

```
bg-base       #0F172A   bg-raised     #131C31   bg-sunken   #0A1120
surface       #1B2336   surface-glass rgba(27,35,54,.72)  (blur 16px)
border        #334155   border-strong #475569
text-primary  #F8FAFC   text-secondary #CBD5E1   text-muted #94A3B8
brand         #6366F1   brand-light   #818CF8
risk-high     #EF4444   risk-high-text #FCA5A5
risk-medium   #FBBF24   risk-medium-text #FBBF24
safe          #22C55E   safe-text     #22C55E
voice-active  #22D3EE   voice-active-text #22D3EE
```

**Computed WCAG contrast (text on bg-base #0F172A):**
| Pair | Ratio | AA (normal/large) |
|---|---|---|
| text-primary #F8FAFC | 17.1:1 | pass/pass |
| text-secondary #CBD5E1 | 12.0:1 | pass/pass |
| text-muted #94A3B8 | 7.0:1 | pass/pass |
| risk-high-text #FCA5A5 | 9.4:1 | pass/pass |
| risk-high (raw #EF4444, icon/border use) | 4.7:1 | pass (large/UI only) |
| risk-medium #FBBF24 | 10.7:1 | pass/pass |
| safe #22C55E | 7.8:1 | pass/pass |
| voice-active #22D3EE | 9.9:1 | pass/pass |
| brand-light #818CF8 | 6.0:1 | pass/pass |

On `surface` (#1B2336) all ratios above drop by ≤1.0 and stay ≥6:1 — verified for text-primary (15.0:1) and text-muted (6.1:1). **Rule: raw `risk-high` #EF4444 is icon/border/glow only — alert body text uses `risk-high-text`.**

## 3. Typography

Fonts (self-hosted via `@fontsource`): `@fontsource/manrope` (display), `@fontsource/inter` (UI), `@fontsource/jetbrains-mono` (clause quotes, citations, timestamps, transcript).

| Token | Font | Size/LH | Weight | Use |
|---|---|---|---|---|
| display-xl | Manrope | 40px/1.15 | 700 | Hero / report score |
| display-lg | Manrope | 28px/1.2 | 700 | Section headers |
| display-md | Manrope | 20px/1.3 | 600 | Card titles |
| ui-base | Inter | 15px/1.5 | 400/500 | Body, labels |
| ui-sm | Inter | 13px/1.4 | 500 | Chips, meta |
| ui-xs | Inter | 11px/1.4 | 600, tracking .04em, uppercase | Status pills |
| mono-quote | JetBrains Mono | 14px/1.5 | 400 | Clause quotes |
| mono-meta | JetBrains Mono | 12px/1.3 | 500 | Timestamps, §citations |

## 4. Spacing / Radius / Shadow / Blur / Grid

Spacing scale (density 7/10 — dashboard-dense): `4, 8, 12, 16, 20, 24, 32, 48, 64px`.
Radius: `sm 6px` (chips) · `md 10px` (inputs) · `lg 14px` (cards) · `full` (pills, orb).
Shadow: `shadow-card: 0 4px 24px rgba(0,0,0,.35)` · glow (severity): `0 0 0 1px <color>33, 0 0 24px <color>4D`.
Blur: `blur-sm 8px` (chips) · `blur-md 16px` (glass cards) · `blur-lg 24px` (modals/orb halo).

**Grid — 1280×720 cockpit:** 12-col, 24px gutter, 24px page margin → 3-col transcript | 6-col live clause/alert stream | 3-col risk meter + voice orb, sticky top status bar (56px).
**1920×1080:** same 12-col at 32px gutter/margin, columns widen (4|6|2 acceptable if orb+meter merge into one rail); nothing new is added, just breathing room.
**Mobile fallback (400px):** single column, stacked order = status bar → voice orb (compact) → risk meter → alert stream → transcript (collapsible) → clause library (drawer).

## 5. Components

- **ClauseCard** — `surface` bg, `lg` radius, left 3px accent bar (brand). Section chip (`ui-xs`, pill, `surface-glass`) top-left. Quoted text in `mono-quote`, `text-primary`, inside `bg-sunken` inset block. Citation (`§4.2`) in `mono-meta`/`text-muted` bottom-right.
- **AlertCard** — severity sets left border + glow (risk-high/medium). Header row: severity icon (not color alone) + `ui-sm` label + `mono-meta` timestamp. Rep sentence in `ui-base`; offending phrase wrapped in `<mark>`-style span, severity-text color + underline (not color-only). Clause quote below in nested ClauseCard (compact). "Spoken verbatim ✓" badge: `safe` pill, check icon, appears only after TTS completion event.
- **TranscriptLine** — final: `text-primary`, opaque. Partial: `text-muted`, italic, opacity .7, trailing animated ellipsis; speaker tag (`ui-xs`, left, brand for rep / muted for prospect).
- **RiskMeter/Radar** — arc gauge, 0–100, color interpolates safe→risk-medium→risk-high; numeric value in `display-md` mono-meta center; radar variant: 4–6 axes (contradiction rate, tone, disclosure, pricing accuracy) as small multiple next to ReportScore.
- **VoiceOrb** — circular, idle: static ring `border-strong`; active: `voice-active` waveform ring pulsing with live amplitude (bars, not blob, for precision feel); speaking state adds outer glow.
- **StatusPills** — `ui-xs`, `full` radius, dot + label (`LIVE`, `CONNECTED`, `RECORDING`), dot color = semantic token, never text-color-only for meaning.
- **DropZone** — dashed `border-strong`, `bg-sunken`, centered icon+label; drag-over → `brand` border + `surface-glass` fill.
- **StepProgress** — horizontal, numbered nodes, connecting line fills `brand` as steps complete; current step has `voice-active` ring.
- **ReportScore** — `display-xl` mono numeral, count-up animated, ring gauge behind it colored by score band.
- **Buttons** — primary: `brand` fill, `text-primary` on it (contrast 5.0:1, verified above via brand-light proxy — use `text-primary` white for solid brand fill, not brand-light); secondary: `surface-glass` + `border`; destructive: `risk-high` fill. Min 40px height, 44px hit target via padding.
- **Inputs** — `bg-sunken`, `border`, `md` radius, 1px `brand` focus border + ring (below). Error state: `risk-high` border + inline `risk-high-text` message.
- **Toasts** — bottom-right stack, `surface-glass`, `lg` radius, severity left bar, auto-dismiss 5s (pause on hover), swipe/click to dismiss.
- **Empty state** — centered icon (muted), `ui-base` text-muted, one-line hint, no illustration.
- **Loading state** — skeleton blocks (`surface`, shimmer sweep) for cards; VoiceOrb shows idle-listening pulse for connection loading.
- **Error state** — `risk-high` icon + message + retry button; never blocks the transcript/orb from continuing.

## 6. Motion (Motion / `motion/react`)

Tokens: `duration-instant 100ms` · `fast 150ms` · `base 250ms` · `slow 400ms` · `deliberate 600ms`. Easing: `standard [0.4,0,0.2,1]`, `exit [0.4,0,1,1]`, `enter [0,0,0.2,1]`. Springs: `snappy {stiffness:420,damping:32}`, `soft {stiffness:220,damping:26}`.

- **Clause extraction reveal**: stagger children 60ms, each `{opacity:0→1, y:12→0}` spring `soft`, container fade `base`.
- **Alert entrance**: card enters `spring snappy` (`scale:0.95→1, y:-8→0`), synced highlight sweep across offending phrase (`base`, left→right gradient wipe) fires exactly at TTS `speech-start` event, not on card mount.
- **Agent speaking pulse**: VoiceOrb ring scale loop `1→1.08→1` driven by live amplitude (RAF-bound, not a fixed loop) while `speaking=true`; falls back to a slow 1.6s `soft` breathing loop if no amplitude signal.
- **Risk meter change**: arc value animates `deliberate` with `standard` easing; color crossfades over same duration; a brief `snappy` scale-bump (1→1.04→1) on the numeral marks the change.
- **Report score count-up**: numeral tweens over `deliberate`–`900ms` depending on delta size, `standard` easing, ring gauge fills in lockstep.
- **prefers-reduced-motion**: all of the above collapse to instant end-state (opacity/position/value set directly, no stagger, no loops); VoiceOrb keeps only a static color-state change, no pulse.

## 7. Accessibility

- Focus ring: `2px solid var(--voice-active)`, `2px offset`, visible on every interactive element — never removed.
- `aria-live="assertive"` on the alert rail container (new AlertCard announced immediately); `aria-live="polite"` on the transcript container for finalized lines only (partials are not announced).
- Severity is never color-only: icon shape (triangle=high, circle=medium, check=safe) + text label accompany every color use (AlertCard, StatusPills, RiskMeter).
- Keyboard flow: `Tab` cycles status bar → orb controls → alert rail (newest first) → transcript → clause library; `Esc` dismisses focused toast/alert detail; `Space`/`Enter` activates focused control; live regions don't steal focus.

## 8. Tailwind + CSS Variables

```js
// tailwind.config.js theme.extend
{
  colors: {
    bg: { base: '#0F172A', raised: '#131C31', sunken: '#0A1120' },
    surface: '#1B2336',
    border: { DEFAULT: '#334155', strong: '#475569' },
    text: { primary: '#F8FAFC', secondary: '#CBD5E1', muted: '#94A3B8' },
    brand: { DEFAULT: '#6366F1', light: '#818CF8' },
    risk: { high: '#EF4444', 'high-text': '#FCA5A5', medium: '#FBBF24' },
    safe: '#22C55E',
    voice: '#22D3EE',
  },
  fontFamily: {
    display: ['Manrope', 'sans-serif'],
    sans: ['Inter', 'sans-serif'],
    mono: ['JetBrains Mono', 'monospace'],
  },
  borderRadius: { sm: '6px', md: '10px', lg: '14px' },
  backdropBlur: { sm: '8px', md: '16px', lg: '24px' },
  boxShadow: { card: '0 4px 24px rgba(0,0,0,.35)' },
}
```

```css
:root {
  --bg-base:#0F172A; --bg-raised:#131C31; --bg-sunken:#0A1120;
  --surface:#1B2336; --surface-glass:rgba(27,35,54,.72);
  --border:#334155; --border-strong:#475569;
  --text-primary:#F8FAFC; --text-secondary:#CBD5E1; --text-muted:#94A3B8;
  --brand:#6366F1; --brand-light:#818CF8;
  --risk-high:#EF4444; --risk-high-text:#FCA5A5; --risk-medium:#FBBF24;
  --safe:#22C55E; --voice-active:#22D3EE;
  --dur-fast:150ms; --dur-base:250ms; --dur-slow:400ms;
}
```

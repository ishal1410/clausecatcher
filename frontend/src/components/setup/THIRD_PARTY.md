# Third-party design credit — setup/

No new npm dependencies were added; only packages already in `package.json`
are used (`react`, `motion`, `lucide-react`, `clsx`/`tailwind-merge` via
`src/lib/cn.ts`), plus the shared `src/components/ui/` kit (`Button`,
`Card`, `Chip`, `motion.ts` tokens) and the `@theme` tokens in
`src/index.css`, both built by the design-system/shell workstream and
consumed here rather than re-implemented.

- **Border-beam effect** (rotating conic-gradient arc behind the newest clause
  card's 1.5px ring, `ClauseList.tsx`) — pattern popularized by Magic UI's
  "Border Beam" component (MIT license,
  https://magicui.design/docs/components/border-beam). No code or package was
  copied; re-implemented from scratch with `motion/react` + CSS `conic-gradient`.
- **Quote highlighter sweep + count-up** (`ClauseList.tsx`) — original
  choreography; the count-up uses Motion's own `animate()` + `useTransform`
  (the same approach as Magic UI's MIT "Number Ticker", concept only, no code
  copied).
- **File-upload drop zone** (`DropZone.tsx`) — interaction shape (dashed
  border, drag-over glow, native `<input type=file>` under a styled label)
  follows the general pattern seen in Aceternity UI and Kokonut UI's
  file-upload components (both MIT-style, code-copy licensed, no paywall on
  the referenced pages per `docs/design_scout/taste.md`). No code was copied;
  implementation is original.
- Icons: `lucide-react` (already a project dependency, ISC license).
- Fonts: Inter Variable, JetBrains Mono, and Manrope — all loaded globally
  via `@fontsource*` imports in `src/index.css` (SIL OFL 1.1) and mapped to
  `font-sans` / `font-mono` / `font-display` in the shared `@theme` block.
  setup/ uses those utility classes directly, no local font wiring needed.

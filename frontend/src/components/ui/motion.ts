/**
 * motion.ts — shared Motion tokens (docs/DESIGN_SYSTEM.md §6), so every
 * component under components/report/ and components/ui/ animates on the
 * same clock instead of hand-rolled durations per file.
 *
 * Reduced motion: App.tsx and Report.tsx wrap their trees in
 * <MotionConfig reducedMotion="user">, which makes Motion drop transform and
 * layout animations (opacity still fades) when the OS asks for less motion.
 * So the variants below can describe the full-motion version only.
 */
import type { Transition, Variants } from 'motion/react'

/** Seconds, for Motion's `transition.duration`. */
export const duration = {
  instant: 0.1,
  fast: 0.15,
  base: 0.25,
  slow: 0.4,
  deliberate: 0.6,
  /** score count-up + ring fill, in lockstep */
  count: 1.1,
} as const

export const easing = {
  standard: [0.4, 0, 0.2, 1],
  exit: [0.4, 0, 1, 1],
  enter: [0, 0, 0.2, 1],
  /** long, quiet deceleration — number count-ups and progress fills */
  outExpo: [0.16, 1, 0.3, 1],
} as const

export const spring = {
  snappy: { type: 'spring', stiffness: 420, damping: 32 } satisfies Transition,
  soft: { type: 'spring', stiffness: 220, damping: 26 } satisfies Transition,
  /** shared-layout moves (selection ring sliding between cards) */
  layout: { type: 'spring', stiffness: 380, damping: 34, mass: 0.8 } satisfies Transition,
} as const

/** Page-level enter/exit used by App.tsx's AnimatePresence step transitions. */
export const pageTransition = {
  initial: { opacity: 0, y: 16 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { ...spring.soft, opacity: { duration: duration.slow, ease: easing.enter } },
  },
  exit: { opacity: 0, y: -8, transition: { duration: duration.fast, ease: easing.exit } },
}

/** Container that cascades its `rise` children (<=0.1s per motion-ui). */
export const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.04 } },
}

/** Child of `stagger`: fade + short rise on a soft spring. */
export const rise: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { ...spring.soft, opacity: { duration: duration.slow, ease: easing.enter } } },
}

/** Staggered children reveal (clause cards, list items). */
export function staggerItem(delayIndex = 0) {
  return {
    initial: { opacity: 0, y: 12 },
    animate: {
      opacity: 1,
      y: 0,
      transition: { ...spring.soft, delay: delayIndex * 0.06 },
    },
  }
}

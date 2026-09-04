import { motion } from 'framer-motion'

/** Thin arc behind the big score number; fills to the score on mount. */
export function ScoreRing({ score, size = 190 }: { score: number | null; size?: number }) {
  const r = (size - 10) / 2
  const c = 2 * Math.PI * r
  const pct = (score ?? 0) / 100
  const tone = score == null ? '#e6e6e6' : score >= 80 ? '#1a9a3c' : score >= 60 ? '#f58a07' : '#e5202a'
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f1f1f1" strokeWidth={6} />
      <motion.circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={tone}
        strokeWidth={6}
        strokeLinecap="round"
        strokeDasharray={c}
        initial={{ strokeDashoffset: c }}
        animate={{ strokeDashoffset: c * (1 - pct) }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1], delay: 0.15 }}
      />
    </svg>
  )
}

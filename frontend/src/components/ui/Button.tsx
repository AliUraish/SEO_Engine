import { AnimatePresence, motion } from 'framer-motion'
import { Check, Loader2 } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'md' | 'sm' | 'icon'

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  variant?: Variant
  size?: Size
  loading?: boolean
  /** Briefly show a check instead of the icon (set true after a successful action). */
  success?: boolean
  icon?: ReactNode
  iconRight?: ReactNode
  children?: ReactNode
}

const variantClass: Record<Variant, string> = {
  primary: 'btn-primary',
  secondary: 'btn-secondary',
  danger: 'btn-danger',
  ghost: 'btn-ghost',
}
const sizeClass: Record<Size, string> = { md: '', sm: 'btn-sm', icon: 'btn-icon' }

/**
 * The one button. Hover: lift + sheen sweep (CSS). Press: spring scale (motion).
 * `loading` swaps the icon for a spinner and keeps the label so the width doesn't jump;
 * `success` swaps in a check that pops.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading, success, icon, iconRight, className, children, disabled, ...rest },
  ref,
) {
  const state = loading ? 'loading' : success ? 'success' : 'idle'
  const leading = state === 'loading' ? <Loader2 className="size-4 animate-spin" /> : state === 'success' ? <Check className="size-4" strokeWidth={3} /> : icon
  return (
    <motion.button
      ref={ref}
      whileTap={disabled || loading ? undefined : { scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      className={cn('btn', variantClass[variant], sizeClass[size], className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...(rest as object)}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        {leading && (
          <motion.span
            key={state + (state === 'idle' ? 'icon' : '')}
            initial={{ scale: 0.4, opacity: 0, rotate: state === 'success' ? -90 : 0 }}
            animate={{ scale: 1, opacity: 1, rotate: 0 }}
            exit={{ scale: 0.4, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 600, damping: 28 }}
            className="inline-flex"
          >
            {leading}
          </motion.span>
        )}
      </AnimatePresence>
      {children && <span>{children}</span>}
      {iconRight && <span className="inline-flex">{iconRight}</span>}
    </motion.button>
  )
})

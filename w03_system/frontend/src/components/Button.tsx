import type { ButtonHTMLAttributes } from 'react'

// ui-guide.md "버튼": Primary = 액션 실행(화면당 하나), Secondary = AI 요청·보조 액션, Text
const VARIANTS = {
  primary: 'rounded-md bg-neutral-900 text-white px-3 h-8 text-sm hover:bg-neutral-700',
  secondary: 'rounded-md border border-neutral-300 bg-white px-3 h-8 text-sm text-neutral-900 hover:bg-neutral-50',
  text: 'text-sm text-neutral-500 hover:text-neutral-900',
} as const

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof VARIANTS }

export function Button({ variant = 'secondary', className = '', type = 'button', ...rest }: Props) {
  return (
    <button
      type={type}
      className={`inline-flex items-center gap-1.5 disabled:opacity-40 disabled:pointer-events-none ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  )
}

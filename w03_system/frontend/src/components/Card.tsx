import type { ReactNode } from 'react'

export function Card({ title, children, className = '' }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg bg-white border border-neutral-200 p-4 space-y-3 ${className}`}>
      {/* 카드 제목은 본문(14px)보다 크고 굵다. 구역이 먼저 읽히게 한다 (ui-guide.md v11) */}
      {title && <h2 className="text-[15px] font-semibold text-neutral-900">{title}</h2>}
      {children}
    </section>
  )
}

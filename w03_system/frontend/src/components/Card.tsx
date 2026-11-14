import type { ReactNode } from 'react'

/** 박스 바깥 왼쪽 위에 놓는 키워드. 박스가 무엇인지는 테두리 밖에서 읽힌다 (ui-guide.md v13) */
export function BoxLabel({ children }: { children: ReactNode }) {
  return <h2 className="px-0.5 text-base font-bold text-neutral-900">{children}</h2>
}

export function Card({ title, children, className = '', boxClassName = '' }: {
  title?: ReactNode; children: ReactNode; className?: string; boxClassName?: string
}) {
  return (
    <section className={`flex flex-col gap-2 ${className}`}>
      {title && <BoxLabel>{title}</BoxLabel>}
      <div className={`flex-1 rounded-lg bg-white border-2 border-neutral-300 shadow-lg/20 p-4 space-y-3 ${boxClassName}`}>{children}</div>
    </section>
  )
}

import type { ReactNode } from 'react'
import { Button } from './Button'

// 되돌릴 수 없는 결정(위원회·SCM 결정, 초기화) 앞의 확인 창. 배경 흐림·글로우 없음, 좌측 정렬.
type Props = {
  open: boolean
  title: string
  children?: ReactNode
  confirmLabel?: string
  busy?: boolean
  confirmDisabled?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({ open, title, children, confirmLabel = '확인', busy = false, confirmDisabled = false, onConfirm, onCancel }: Props) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 bg-neutral-900/30" onClick={busy ? undefined : onCancel}>
      <div className="max-w-7xl mx-auto px-6 pt-24">
        <div
          role="dialog"
          aria-modal="true"
          className="max-w-md rounded-lg bg-white border border-neutral-200 p-4 space-y-3"
          onClick={e => e.stopPropagation()}
        >
          <h2 className="text-sm font-medium text-neutral-900">{title}</h2>
          {children && <div className="text-sm text-neutral-700 leading-relaxed space-y-2">{children}</div>}
          <div className="flex gap-2 pt-1">
            <Button variant="primary" onClick={onConfirm} disabled={busy || confirmDisabled}>
              {busy ? '실행 중…' : confirmLabel}
            </Button>
            <Button variant="text" onClick={onCancel} disabled={busy}>취소</Button>
          </div>
        </div>
      </div>
    </div>
  )
}

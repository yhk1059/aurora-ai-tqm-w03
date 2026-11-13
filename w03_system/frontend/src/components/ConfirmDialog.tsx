import type { ReactNode } from 'react'
import { Button } from './Button'

// 되돌릴 수 없는 결정(위원회·SCM 결정, 초기화) 앞의 확인 창. 배경 흐림·글로우 없음. 창은 화면 가운데, 내용은 좌측 정렬.
// 아래 줄: 왼쪽에 주의 문구, 오른쪽에 취소 → 실행 순서 (ui-guide.md v4).
type Props = {
  open: boolean
  title: string
  children?: ReactNode
  confirmLabel?: string
  busy?: boolean
  confirmDisabled?: boolean
  /** 근거와 입력을 함께 담는 결정 창은 넓게 */
  wide?: boolean
  /** 실행 버튼 왼쪽의 주의 문구 */
  note?: ReactNode
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({ open, title, children, confirmLabel = '확인', busy = false, confirmDisabled = false, wide = false, note, onConfirm, onCancel }: Props) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 bg-neutral-900/30" onClick={busy ? undefined : onCancel}>
      <div className={`flex justify-center px-6 ${wide ? 'pt-10' : 'pt-24'}`}>
        <div
          role="dialog"
          aria-modal="true"
          className={`w-full ${wide ? 'max-w-3xl max-h-[calc(100vh-5rem)]' : 'max-w-lg max-h-[calc(100vh-8rem)]'} overflow-y-auto rounded-lg bg-white border border-neutral-200 p-5 space-y-3`}
          onClick={e => e.stopPropagation()}
        >
          <h2 className="text-lg font-semibold text-neutral-900">{title}</h2>
          {children && <div className="text-sm text-neutral-700 leading-relaxed space-y-2">{children}</div>}
          <div className="flex items-center gap-2 border-t border-neutral-200 pt-3">
            {note && <span className="text-xs text-amber-700">{note}</span>}
            <span className="flex-1" />
            <Button variant="secondary" className="h-10 px-4" onClick={onCancel} disabled={busy}>취소</Button>
            <Button variant="primary" className="h-10 px-5 font-medium" onClick={onConfirm} disabled={busy || confirmDisabled}>
              {busy ? '실행 중…' : confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

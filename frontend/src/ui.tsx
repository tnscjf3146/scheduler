import { useEffect, type ReactNode } from 'react'

export function Widget({ title, action, children }: { title: ReactNode; action?: ReactNode; children?: ReactNode }) {
  return (
    <section className="flex min-h-0 flex-1 flex-col gap-2.5 rounded-xl border border-neutral-200 bg-white p-3.5">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-neutral-900">{title}</h2>
        {action}
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">{children}</div>
    </section>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-xs text-neutral-400">{children}</p>
}

export function LinkButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} className="text-xs text-neutral-500 hover:text-neutral-900 disabled:opacity-40" />
}

export function Button({ variant = 'primary', ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' }) {
  const style =
    variant === 'primary'
      ? 'bg-neutral-800 text-white hover:bg-neutral-700'
      : 'border border-neutral-300 bg-white text-neutral-900 hover:bg-neutral-50'
  return <button {...props} className={`shrink-0 rounded-md px-3.5 py-1.5 text-xs font-medium disabled:opacity-40 ${style}`} />
}

export const inputClass =
  'rounded-md border border-neutral-300 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-neutral-600'

/** The house popup size: a share of the app window, so every popup grows and shrinks with it. */
export const POPUP_SIZE = 'h-[81vh] w-[83vw]'
/** Dimmed backdrop behind every popup. */
export const POPUP_BACKDROP = 'fixed inset-0 z-10 flex items-center justify-center bg-neutral-900/45'

export function Modal({ title, onClose, children, footer }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className={POPUP_BACKDROP} onMouseDown={onClose}>
      <div className={`flex ${POPUP_SIZE} flex-col overflow-hidden rounded-xl bg-white shadow-xl`} onMouseDown={(e) => e.stopPropagation()}>
        <header className="flex items-start gap-3 px-6 pt-5 pb-4">
          <div className="min-w-0 flex-1">{title}</div>
          <button onClick={onClose} className="text-lg leading-none text-neutral-400 hover:text-neutral-800" aria-label="닫기">
            ✕
          </button>
        </header>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 pb-5">{children}</div>
        {footer && <footer className="flex items-center gap-2 bg-neutral-100 px-6 py-3">{footer}</footer>}
      </div>
    </div>
  )
}

export function Section({ title, tag, children }: { title: string; tag?: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-[13px] font-bold">
        {title}
        {tag && <span className="rounded border border-neutral-300 px-1.5 text-[10px] font-medium text-neutral-500">{tag}</span>}
      </h3>
      {children}
    </section>
  )
}

export function ErrorText({ error }: { error: string | null }) {
  return error ? <p className="text-xs text-red-600">{error}</p> : null
}

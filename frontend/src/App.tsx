import { useEffect, useState, type ReactNode } from 'react'

function Widget({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <section className="flex min-h-0 flex-1 flex-col gap-2.5 rounded-xl border border-neutral-200 bg-white p-3.5">
      <h2 className="text-sm font-bold text-neutral-900">{title}</h2>
      {children}
    </section>
  )
}

function Column({ width, children }: { width: string; children: ReactNode }) {
  return <div className={`flex min-h-0 flex-col gap-4 ${width}`}>{children}</div>
}

export default function App() {
  const [api, setApi] = useState('연결 확인 중')

  useEffect(() => {
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(() => setApi('API 연결됨'))
      .catch(() => setApi('API 연결 안 됨'))
  }, [])

  return (
    <div className="flex h-full flex-col bg-neutral-100 text-neutral-900">
      <header className="flex items-center gap-4 border-b border-neutral-200 bg-white px-6 py-3.5">
        <span className="text-base font-bold">Scheduler</span>
        <span className="ml-auto text-xs text-neutral-500">{api}</span>
      </header>

      <main className="flex min-h-0 flex-1 gap-4 p-4">
        <Column width="w-[300px]">
          <Widget title="다가오는 일정" />
          <Widget title="Agent" />
        </Column>
        <Column width="w-[380px]">
          <Widget title="할 일" />
          <Widget title="일정 (달력)" />
        </Column>
        <Column width="w-[320px]">
          <Widget title="메일 검토" />
          <Widget title="결재 대기" />
        </Column>
        <aside className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl bg-neutral-900">
          <div className="border-b border-neutral-800 px-3.5 py-3 text-sm text-neutral-400">에이전트를 선택하세요</div>
        </aside>
      </main>
    </div>
  )
}

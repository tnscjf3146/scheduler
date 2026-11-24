import { useEffect, useState } from 'react'
import { api, dateKey, formatWhen, type Todo } from './api'
import { Button, Empty, ErrorText, Widget, inputClass } from './ui'

export function Upcoming({ todos }: { todos: Todo[] }) {
  const [items, setItems] = useState<Todo[]>([])
  useEffect(() => {
    api<Todo[]>('/api/todos/upcoming').then(setItems, () => setItems([]))
  }, [todos])

  return (
    <Widget title="다가오는 일정">
      {items.length === 0 && <Empty>다가오는 일정이 없습니다</Empty>}
      {items.map((t) => (
        <div key={t.id} className="rounded-md bg-neutral-100 px-3 py-2.5">
          <p className="truncate text-[13px] font-medium">{t.title}</p>
          <p className="text-[11px] text-neutral-500">{formatWhen(t.due_at!)}</p>
        </div>
      ))}
    </Widget>
  )
}

export function Todos({ todos, reload }: { todos: Todo[]; reload: () => void }) {
  const [title, setTitle] = useState('')
  const [due, setDue] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function add(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    try {
      await api('/api/todos', { method: 'POST', json: { title, due_at: due || null } })
      setTitle('')
      setDue('')
      setError(null)
      reload()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const toggle = (t: Todo) => api(`/api/todos/${t.id}`, { method: 'PATCH', json: { done: !t.done } }).then(reload)
  const remove = (t: Todo) => api(`/api/todos/${t.id}`, { method: 'DELETE' }).then(reload)

  return (
    <Widget title="할 일">
      <form onSubmit={add} className="flex gap-2">
        <input className={`${inputClass} min-w-0 flex-1`} placeholder="할 일 제목" value={title} onChange={(e) => setTitle(e.target.value)} />
        <input className={`${inputClass} w-[150px]`} type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
        <Button type="submit" disabled={!title.trim()}>
          추가
        </Button>
      </form>
      <ErrorText error={error} />
      {todos.length === 0 && <Empty>할 일이 없습니다</Empty>}
      {todos.map((t) => (
        <div key={t.id} className="group flex items-center gap-2.5 rounded-md bg-neutral-100 px-3 py-2.5">
          <input type="checkbox" checked={t.done} onChange={() => toggle(t)} className="size-3.5 accent-neutral-800" />
          <div className="min-w-0 flex-1">
            <p className={`truncate text-[13px] font-medium ${t.done ? 'text-neutral-400 line-through' : ''}`}>{t.title}</p>
            <p className="text-[11px] text-neutral-500">{t.due_at ? formatWhen(t.due_at) : '날짜 없음'}</p>
          </div>
          <button onClick={() => remove(t)} className="invisible text-xs text-neutral-400 group-hover:visible hover:text-neutral-800" aria-label="삭제">
            ✕
          </button>
        </div>
      ))}
    </Widget>
  )
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

export function Calendar({ todos }: { todos: Todo[] }) {
  const [month, setMonth] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })
  const byDay = new Map<string, Todo[]>()
  for (const t of todos) {
    if (!t.due_at) continue
    const key = t.due_at.slice(0, 10)
    byDay.set(key, [...(byDay.get(key) ?? []), t])
  }
  const start = new Date(month.getFullYear(), month.getMonth(), 1 - month.getDay())
  const weeks = Math.ceil((month.getDay() + new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()) / 7)
  const today = dateKey(new Date())
  const shift = (n: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1))

  return (
    <Widget title="일정 (달력)">
      <div className="flex items-center justify-between">
        <button onClick={() => shift(-1)} className="px-2 text-neutral-400 hover:text-neutral-900" aria-label="이전 달">
          ‹
        </button>
        <span className="text-[13px] font-medium">
          {month.getFullYear()}년 {month.getMonth() + 1}월
        </span>
        <button onClick={() => shift(1)} className="px-2 text-neutral-400 hover:text-neutral-900" aria-label="다음 달">
          ›
        </button>
      </div>
      <div className="grid grid-cols-7 text-center text-[10px] font-medium text-neutral-500">
        {WEEKDAYS.map((w) => (
          <span key={w}>{w}</span>
        ))}
      </div>
      <div className="grid flex-1 grid-cols-7 border-t border-l border-neutral-200" style={{ gridTemplateRows: `repeat(${weeks}, minmax(44px, 1fr))` }}>
        {Array.from({ length: weeks * 7 }, (_, i) => {
          const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i)
          const key = dateKey(d)
          const items = byDay.get(key) ?? []
          const inMonth = d.getMonth() === month.getMonth()
          return (
            <div key={key} className={`flex min-w-0 flex-col gap-0.5 border-r border-b border-neutral-200 p-1 ${inMonth ? '' : 'bg-neutral-50'}`}>
              <span className={`text-[10px] ${key === today ? 'font-bold text-neutral-900' : inMonth ? 'text-neutral-500' : 'text-neutral-300'}`}>{d.getDate()}</span>
              {items.slice(0, 2).map((t) => (
                <span key={t.id} title={t.title} className={`truncate rounded-sm px-1 text-[9px] leading-4 ${t.done ? 'bg-neutral-100 text-neutral-400' : 'bg-neutral-800 text-white'}`}>
                  {t.title}
                </span>
              ))}
              {items.length > 2 && <span className="text-[9px] text-neutral-400">+{items.length - 2}</span>}
            </div>
          )
        })}
      </div>
    </Widget>
  )
}

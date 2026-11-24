import { useEffect, useRef, useState } from 'react'
import { api, dateKey, type Todo } from './api'
import { Button, Empty, ErrorText, POPUP_BACKDROP, POPUP_SIZE, Widget, inputClass } from './ui'

/** Timeline by day: a dot per date (filled for today), then `time  title` rows. */
export function Upcoming({ todos, onOpen }: { todos: Todo[]; onOpen: (id: string) => void }) {
  const [items, setItems] = useState<Todo[]>([])
  useEffect(() => {
    api<Todo[]>('/api/todos/upcoming').then(setItems, () => setItems([]))
  }, [todos])

  return (
    <Widget title="다가오는 일정">
      {items.length === 0 && <Empty>다가오는 일정이 없습니다</Empty>}
      {byDay(items).map(([day, dayItems]) => (
        <section key={day} className="ml-1.5 border-l-2 border-neutral-200 pl-3">
          <h3 className="-ml-[19px] flex items-center gap-2 py-1 text-xs font-bold">
            <span className={`size-3 shrink-0 rounded-full border-2 ${day === dateKey(new Date()) ? 'border-white bg-neutral-800 ring-1 ring-neutral-800' : 'border-neutral-400 bg-white'}`} />
            {dayLabel(day)}
          </h3>
          {dayItems.map((t) => (
            <button key={t.id} type="button" onClick={() => onOpen(t.id)} title={t.title} className="flex w-full items-baseline gap-2 py-1 text-left hover:underline">
              <span className="w-9 shrink-0 text-[11px] text-neutral-500">{t.due_at!.slice(11, 16)}</span>
              <span className="line-clamp-2 min-w-0 flex-1 text-[13px] leading-snug font-medium break-all">{t.title}</span>
            </button>
          ))}
        </section>
      ))}
    </Widget>
  )
}

const TITLE_MAX = 40 // keeps a title within two lines of the todo list; same limit as the server (todos.py)

export function Todos({ todos, reload, onOpen }: { todos: Todo[]; reload: () => void; onOpen: (id: string) => void }) {
  const [title, setTitle] = useState('')
  const [due, setDue] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function add(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    try {
      await api('/api/todos', {
        method: 'POST',
        json: { title, due_at: due || null },
      })
      setTitle('')
      setDue('')
      setError(null)
      reload()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const remove = (t: Todo) => api(`/api/todos/${t.id}`, { method: 'DELETE' }).then(reload)

  const [showDone, setShowDone] = useState(false)
  const shown = todos.filter((t) => t.done === showDone)
  const tab = (done: boolean, label: string) => (
    <button type="button" onClick={() => setShowDone(done)} aria-pressed={showDone === done} className={showDone === done ? 'text-neutral-900' : 'font-medium text-neutral-400 hover:text-neutral-700'}>
      {label}
    </button>
  )

  return (
    <Widget
      title={
        <span className="flex gap-3">
          {tab(false, '할 일')}
          {tab(true, '완료한 일')}
        </span>
      }
    >
      {!showDone && (
        <form onSubmit={add} className="flex gap-2">
          <input className={`${inputClass} min-w-0 flex-1`} placeholder={`할 일 제목 (${TITLE_MAX}자까지)`} maxLength={TITLE_MAX} value={title} onChange={(e) => setTitle(e.target.value)} />
          <input className={`${inputClass} w-[150px]`} type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
          <Button type="submit" disabled={!title.trim()}>
            추가
          </Button>
        </form>
      )}
      <ErrorText error={error} />
      {shown.length === 0 && <Empty>{showDone ? '완료한 일이 없습니다' : '할 일이 없습니다'}</Empty>}
      {/* Date on its own line, that day's todos indented under it. */}
      <div className="flex flex-col gap-2">
        {byDay(shown).map(([day, items]) => (
          <section key={day || 'none'}>
            <h3 className="py-1 text-xs font-semibold text-neutral-400">{day ? dayLabel(day) : '날짜 없음'}</h3>
            <div className="divide-y divide-neutral-100 pl-4">
              {items.map((t) => (
                <div key={t.id} className="group flex items-center gap-2 py-2">
                  <button
                    type="button"
                    onClick={() => onOpen(t.id)}
                    title={t.title}
                    className={`line-clamp-2 min-w-0 flex-1 text-left text-[13px] leading-snug font-medium break-all hover:underline ${t.done ? 'text-neutral-400 line-through' : ''}`}
                  >
                    {t.title}
                  </button>
                  {t.subtasks.length > 0 && (
                    <span className="shrink-0 text-[10px] text-neutral-400">
                      {t.subtasks.filter((s) => s.done).length}/{t.subtasks.length}
                    </span>
                  )}
                  {t.due_at && <span className="shrink-0 text-[11px] text-neutral-500">{t.due_at.slice(11, 16)}</span>}
                  <button onClick={() => remove(t)} className="invisible text-xs text-neutral-400 group-hover:visible hover:text-neutral-800" aria-label="삭제">
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Widget>
  )
}

/**
 * Three panels: info (title, date, actions) | memo | subtasks.
 * Title, date and memo are a draft saved by "저장 후 닫기"; closing any other way drops it.
 * Clicks (완료, subtask checks, adding or removing a subtask) save at once.
 */
export function TodoDetail({ todo, onClose, reload }: { todo: Todo; onClose: () => void; reload: () => void }) {
  const [title, setTitle] = useState(todo.title)
  const [due, setDue] = useState(todo.due_at ?? '')
  const [memo, setMemo] = useState(todo.memo)
  const [newSub, setNewSub] = useState('')
  const [error, setError] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function patch(fields: Partial<Pick<Todo, 'title' | 'due_at' | 'done' | 'memo' | 'subtasks'>>) {
    try {
      await api(`/api/todos/${todo.id}`, { method: 'PATCH', json: fields })
      setError(null)
      reload()
      return true
    } catch (err) {
      setError((err as Error).message)
      return false
    }
  }
  const setSubtasks = (subtasks: Todo['subtasks']) => patch({ subtasks })

  async function saveAndClose() {
    if (!title.trim()) return setError('제목을 적어 주세요')
    const changes: Partial<Todo> = {}
    if (title.trim() !== todo.title) changes.title = title.trim()
    if ((due || null) !== todo.due_at) changes.due_at = due || null
    if (memo !== todo.memo) changes.memo = memo
    if (Object.keys(changes).length && !(await patch(changes))) return
    onClose()
  }

  async function remove() {
    if (!window.confirm(`'${todo.title}'을(를) 삭제할까요?`)) return
    await api(`/api/todos/${todo.id}`, { method: 'DELETE' })
    reload()
    onClose()
  }

  const when = due ? new Date(due) : null
  const doneCount = todo.subtasks.filter((s) => s.done).length
  return (
    <div className={POPUP_BACKDROP} onMouseDown={onClose}>
      <div
        role="dialog"
        aria-label="할 일 상세"
        onMouseDown={(e) => e.stopPropagation()}
        className={`grid ${POPUP_SIZE} grid-cols-[minmax(220px,22%)_minmax(0,1fr)_minmax(260px,30%)] overflow-hidden rounded-xl bg-white shadow-xl`}
      >
        <aside className="flex min-h-0 flex-col gap-3.5 border-r border-neutral-100 px-5 pt-6 pb-5">
          <textarea
            value={title}
            maxLength={TITLE_MAX}
            rows={2}
            onChange={(e) => setTitle(e.target.value.replace(/\n/g, ''))}
            aria-label="제목"
            className={`-mx-1 resize-none rounded-md px-1 text-xl leading-snug font-bold outline-none hover:bg-neutral-50 focus:bg-neutral-50 ${todo.done ? 'text-neutral-400 line-through' : ''}`}
          />
          <div className="flex flex-col gap-1 border-t border-neutral-100 pt-3.5">
            <button type="button" onClick={() => picker.current?.showPicker()} className="w-fit text-left hover:underline" title="날짜 바꾸기">
              <span className="block text-[17px] leading-snug font-semibold">{when ? `${when.getMonth() + 1}월 ${when.getDate()}일` : '날짜 없음'}</span>
              {when && (
                <span className="block text-[13px] text-neutral-600">
                  {WEEKDAYS[when.getDay()]}요일 · {due.slice(11, 16)}
                </span>
              )}
            </button>
            <input ref={picker} type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} className="sr-only" tabIndex={-1} aria-label="날짜" />
            {due && (
              <button type="button" onClick={() => setDue('')} className="w-fit text-[11px] text-neutral-400 hover:text-neutral-700">
                날짜 지우기
              </button>
            )}
          </div>
          <span className="flex-1" />
          <ErrorText error={error} />
          <button type="button" onClick={saveAndClose} className="rounded-lg border border-neutral-300 bg-white py-2.5 text-sm font-semibold text-neutral-800 hover:bg-neutral-50">
            저장 후 닫기
          </button>
          <button
            type="button"
            onClick={() => patch({ done: !todo.done })}
            className={`rounded-lg py-2.5 text-sm font-semibold ${todo.done ? 'border border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-50' : 'bg-neutral-800 text-white hover:bg-neutral-700'}`}
          >
            {todo.done ? '완료 취소' : '완료'}
          </button>
          <button type="button" onClick={remove} className="text-[13px] text-red-700 hover:underline">
            삭제
          </button>
        </aside>

        <section className="flex min-h-0 flex-col gap-2 px-6 pt-6 pb-5">
          <h3 className="text-[13px] font-bold text-neutral-500">메모</h3>
          <textarea
            value={memo}
            maxLength={2000}
            onChange={(e) => setMemo(e.target.value)}
            placeholder="메모를 적으세요"
            className="min-h-0 flex-1 resize-none rounded-lg border border-neutral-200 p-3.5 text-sm leading-relaxed outline-none focus:border-neutral-500"
          />
        </section>

        <section className="relative flex min-h-0 flex-col gap-2.5 border-l border-neutral-100 bg-neutral-50 px-5 pt-6 pb-5">
          <button onClick={onClose} className="absolute top-4 right-4 p-1 text-base leading-none text-neutral-400 hover:text-neutral-800" aria-label="닫기">
            ✕
          </button>
          <h3 className="text-[13px] font-bold">
            하위 할 일{' '}
            {todo.subtasks.length > 0 && (
              <span className="text-xs font-normal text-neutral-500">
                {doneCount} / {todo.subtasks.length}
              </span>
            )}
          </h3>
          <div className="flex min-h-0 flex-col overflow-y-auto rounded-lg border border-neutral-200 bg-white">
            {todo.subtasks.map((s, i) => (
              <div key={i} className="group flex items-center gap-2.5 border-b border-neutral-100 px-3.5 py-2.5">
                <input
                  type="checkbox"
                  checked={s.done}
                  onChange={() => setSubtasks(todo.subtasks.map((x, j) => (j === i ? { ...x, done: !x.done } : x)))}
                  className="size-3.5 shrink-0 accent-neutral-800"
                />
                <span className={`min-w-0 flex-1 text-sm break-all ${s.done ? 'text-neutral-400 line-through' : ''}`}>{s.title}</span>
                <button
                  onClick={() => setSubtasks(todo.subtasks.filter((_, j) => j !== i))}
                  className="invisible text-xs text-neutral-400 group-hover:visible hover:text-neutral-800"
                  aria-label="하위 할 일 삭제"
                >
                  ✕
                </button>
              </div>
            ))}
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (!newSub.trim()) return
                setSubtasks([...todo.subtasks, { title: newSub.trim(), done: false }])
                setNewSub('')
              }}
            >
              <input
                value={newSub}
                maxLength={TITLE_MAX}
                onChange={(e) => setNewSub(e.target.value)}
                placeholder="+ 하위 할 일 추가"
                aria-label="하위 할 일 추가"
                className="w-full bg-transparent px-3.5 py-2.5 text-[13px] outline-none"
              />
            </form>
          </div>
        </section>
      </div>
    </div>
  )
}

/** Groups todos by due date, in the order given (dated first, by time); undated ones go last under ''. */
function byDay(todos: Todo[]): [string, Todo[]][] {
  const groups = new Map<string, Todo[]>()
  for (const t of todos) {
    const day = t.due_at?.slice(0, 10) ?? ''
    groups.set(day, [...(groups.get(day) ?? []), t])
  }
  return [...groups].sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)))
}

function dayLabel(day: string): string {
  const d = new Date(`${day}T00:00`)
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${WEEKDAYS[d.getDay()]}요일`
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
  const [selected, setSelected] = useState(today)
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
            <button
              key={key}
              type="button"
              onClick={() => setSelected(key)}
              aria-pressed={key === selected}
              className={`flex min-w-0 flex-col gap-0.5 border-r border-b border-neutral-200 p-1 text-left ${key < today ? 'bg-neutral-100' : inMonth ? '' : 'bg-neutral-50'} ${key === selected ? 'outline-2 -outline-offset-2 outline-neutral-800' : ''}`}
            >
              <span className={`text-[10px] ${key === selected ? 'font-bold' : ''} ${key === today || key === selected ? 'text-neutral-900' : inMonth ? 'text-neutral-500' : 'text-neutral-300'}`}>
                {d.getDate()}
              </span>
              {items.slice(0, 2).map((t) => (
                <span key={t.id} title={t.title} className={`truncate rounded-sm px-1 text-[9px] leading-4 ${t.done ? 'bg-neutral-100 text-neutral-400' : 'bg-neutral-800 text-white'}`}>
                  {t.title}
                </span>
              ))}
              {items.length > 2 && <span className="text-[9px] text-neutral-400">+{items.length - 2}</span>}
            </button>
          )
        })}
      </div>
    </Widget>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { Agents } from './agents'
import { api, type Agent, type Todo } from './api'
import { Approvals } from './approvals'
import { MailReview } from './mail'
import { TerminalPanel } from './terminal'
import { Calendar, Todos, Upcoming } from './todos'

function Clock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(timer)
  }, [])
  const day = ['일', '월', '화', '수', '목', '금', '토'][now.getDay()]
  const time = now.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })
  return (
    <span className="text-[13px] text-neutral-500">
      {now.getMonth() + 1}월 {now.getDate()}일 ({day}) · {time}
    </span>
  )
}

export default function App() {
  const [todos, setTodos] = useState<Todo[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [selected, setSelected] = useState<string | null>(null)

  const loadTodos = useCallback(() => api<Todo[]>('/api/todos').then(setTodos, () => {}), [])
  const loadAgents = useCallback(() => api<Agent[]>('/api/agents').then(setAgents, () => {}), [])

  useEffect(() => {
    loadTodos()
    loadAgents()
    const timer = setInterval(loadAgents, 5_000) // session status changes on its own (CLI exits etc.)
    return () => clearInterval(timer)
  }, [loadTodos, loadAgents])

  const agent = agents.find((a) => a.id === selected) ?? null

  return (
    <div className="flex h-full flex-col bg-neutral-100 text-neutral-900">
      <header className="flex items-center gap-4 border-b border-neutral-200 bg-white px-6 py-3">
        <span className="flex items-center gap-2 text-base font-bold">
          <img src="/logo.svg" alt="" className="size-6" />
          Scheduler
        </span>
        <Clock />
      </header>

      <main className="flex min-h-0 flex-1 gap-4 p-4">
        <div className="flex w-[300px] min-h-0 shrink-0 flex-col gap-4">
          <Upcoming todos={todos} />
          <Agents agents={agents} selected={selected} onSelect={setSelected} reload={loadAgents} />
        </div>
        <div className="flex w-[380px] min-h-0 shrink-0 flex-col gap-4">
          <Todos todos={todos} reload={loadTodos} />
          <Calendar todos={todos} />
        </div>
        <div className="flex w-[320px] min-h-0 shrink-0 flex-col gap-4">
          <MailReview />
          <Approvals />
        </div>
        <TerminalPanel agent={agent} onStatus={loadAgents} />
      </main>
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { Agents } from './agents'
import { api, type Agent, type Todo } from './api'
import { Approvals } from './approvals'
import { MailReview } from './mail'
import { TerminalPanel } from './terminal'
import { Calendar, TodoDetail, Todos, Upcoming } from './todos'

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
  // The todo whose detail popup is open, by id so it follows the latest data (agents change todos too).
  const [openTodo, setOpenTodo] = useState<string | null>(null)
  const [restarts, setRestarts] = useState(0) // bumping it remounts the terminal, which reconnects to a new session

  const loadTodos = useCallback(() => api<Todo[]>('/api/todos').then(setTodos, () => {}), [])
  const loadAgents = useCallback(() => api<Agent[]>('/api/agents').then(setAgents, () => {}), [])

  useEffect(() => {
    loadTodos()
    loadAgents()
    // Both change outside this page: session status on its own (CLI exits etc.), todos through agents' MCP tools.
    const timer = setInterval(() => {
      loadAgents()
      loadTodos()
    }, 5_000)
    return () => clearInterval(timer)
  }, [loadTodos, loadAgents])

  const agent = agents.find((a) => a.id === selected) ?? null
  const opened = todos.find((t) => t.id === openTodo)

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
        <div className="flex min-w-0 min-h-0 flex-[30] flex-col gap-4">
          <Upcoming todos={todos} onOpen={setOpenTodo} />
          <Agents agents={agents} selected={selected} onSelect={setSelected} onRestarted={() => setRestarts((n) => n + 1)} reload={loadAgents} />
        </div>
        <div className="flex min-w-0 min-h-0 flex-[38] flex-col gap-4">
          <Todos todos={todos} reload={loadTodos} onOpen={setOpenTodo} />
          <Calendar todos={todos} />
        </div>
        <div className="flex min-w-0 min-h-0 flex-[32] flex-col gap-4">
          <MailReview agents={agents} onOpenAgent={setSelected} />
          <Approvals />
        </div>
        <TerminalPanel key={restarts} agent={agent} onStatus={loadAgents} />
      </main>
      {opened && <TodoDetail key={opened.id} todo={opened} onClose={() => setOpenTodo(null)} reload={loadTodos} />}
    </div>
  )
}

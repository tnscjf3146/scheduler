import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import type { Agent } from './api'
import { CLI_LABEL } from './agents'
import { TerminalView } from './terminal'

/** A Claude Code agent's terminal, shown as a chat (backend/app/chat.py, design: terminal-chat-design.md).
 * The agent runs in its real terminal; the chat reads its transcript, its hooks, and the cards it makes itself. */

type Action = { kind: 'send'; text: string } | { kind: 'open_todo'; id: string } | { kind: 'open_mail'; id: string } | { kind: 'link'; url: string }
type Part =
  | { type: 'text'; text: string }
  | { type: 'fields'; rows: { label: string; value: string }[] }
  | { type: 'list'; items: { text: string; sub?: string; action?: Action }[] }
  | { type: 'date'; date: string; label?: string }
  | { type: 'todo'; id: string; data: { id: string; title: string; due_at: string | null; done: boolean } | null }
  | { type: 'mail'; id: string; data: { id: string; subject: string; sender: string; received_at: string; account: string } | null }
  | { type: 'buttons'; buttons: { label: string; action: Action }[] }
  | { type: 'html'; html: string }
type Card = { title?: string; parts: Part[] }

type ChatEvent = { id: string; at: string } & (
  | { kind: 'user' | 'text' | 'note'; text: string; shown?: { label: string; title: string; request: string } }
  | { kind: 'tool'; name: string; input: Record<string, unknown>; status: 'running' | 'done' | 'error'; result?: string }
  | { kind: 'card'; card: Card }
  | { kind: 'question'; question: string; detail: string; options: string[]; status: 'pending' | 'answered' | 'unanswered'; answer?: string | null }
  | { kind: 'permission'; name: string; input: Record<string, unknown>; status: 'pending' | 'allowed' | 'denied' | 'terminal' }
  | { kind: 'done'; ms: number | null }
)
type ToolEvent = Extract<ChatEvent, { kind: 'tool' }>

/** A request and everything the agent did for it. Events before the first request form a turn with no request. */
type Turn = { request?: ChatEvent; tools: ToolEvent[]; items: ChatEvent[]; ms: number | null; finished: boolean }

function toTurns(events: ChatEvent[]): Turn[] {
  const turns: Turn[] = []
  for (const e of events) {
    if (e.kind === 'user' || turns.length === 0) turns.push({ request: e.kind === 'user' ? e : undefined, tools: [], items: [], ms: null, finished: false })
    const turn = turns[turns.length - 1]
    if (e.kind === 'user') continue
    // The card tools show up as cards and questions themselves: no step for them.
    if (e.kind === 'tool') {
      if (!e.name.endsWith('__show_card') && !e.name.endsWith('__ask_user')) turn.tools.push(e)
    } else if (e.kind === 'done') {
      turn.ms = e.ms
      turn.finished = true
    } else turn.items.push(e)
  }
  return turns
}

const SCHEDULER_LABEL: Record<string, string> = {
  list_todos: '할 일 보기', add_todo: '할 일 추가', update_todo: '할 일 수정', delete_todo: '할 일 삭제',
  list_forms: '양식 보기', submit_approval: '결재 올림', get_approval: '결재 확인',
  list_extensions: '스킬 보기', create_skill: '스킬 만들기', create_hook: '하네스 만들기', list_agents: '에이전트 보기', create_agent: '에이전트 만들기',
  list_mail_accounts: '메일 계정 보기', add_mail_account: '메일 계정 연결', delete_mail_account: '메일 계정 해제',
  list_mails: '메일 목록', read_mail: '메일 읽기', sync_mail: '새 메일 받기', reply_mail: '답장 보내기', forward_mail: '메일 전달',
  list_mail_folders: '메일 폴더 보기', create_mail_folder: '메일 폴더 만들기', rename_mail_folder: '메일 폴더 이름 바꾸기',
  delete_mail_folder: '메일 폴더 삭제', subscribe_mail_folder: '메일 폴더 표시', mail_quota: '메일 용량 보기',
  search_mailbox: '메일 검색', read_mailbox_mail: '메일 읽기', set_mail_flags: '메일 표시', move_mail: '메일 옮기기',
  delete_mail: '메일 삭제', save_mail_draft: '초안 저장',
}
const BUILTIN_LABEL: Record<string, string> = {
  Bash: '명령 실행', PowerShell: '명령 실행', Read: '파일 읽기', Write: '파일 만들기', Edit: '파일 수정', MultiEdit: '파일 수정',
  NotebookEdit: '노트북 수정', Glob: '파일 찾기', Grep: '내용 찾기', WebFetch: '웹 페이지 읽기', WebSearch: '웹 검색',
  Task: '하위 작업', Agent: '하위 작업', TodoWrite: '작업 목록 정리', Skill: '스킬 읽기', ToolSearch: '도구 찾기', TrustFolder: '이 폴더에서 일하기',
}

function toolLabel(name: string): string {
  if (name.startsWith('mcp__scheduler__')) return SCHEDULER_LABEL[name.slice(16)] ?? name.slice(16)
  if (name.startsWith('mcp__claude-in-chrome__')) return '브라우저 조작'
  if (name.startsWith('mcp__')) return name.split('__').slice(2).join(' ')
  return BUILTIN_LABEL[name] ?? name
}

function toolDetail(input: Record<string, unknown>): string {
  const pick = ['command', 'file_path', 'path', 'title', 'query', 'subject', 'url', 'pattern', 'skill', 'description', 'to', 'name']
    .map((k) => input[k])
    .find((v) => typeof v === 'string' && v)
  return typeof pick === 'string' ? pick : ''
}

const seconds = (ms: number | null) => (ms == null ? '' : ms < 60_000 ? `${Math.max(1, Math.round(ms / 1000))}초` : `${Math.round(ms / 60_000)}분`)
const DAY = ['일', '월', '화', '수', '목', '금', '토']
const two = (n: number) => String(n).padStart(2, '0')
const whenText = (d: Date, withTime: boolean) => `${d.getMonth() + 1}/${d.getDate()}(${DAY[d.getDay()]})${withTime ? ` ${two(d.getHours())}:${two(d.getMinutes())}` : ''}`

/** Light markdown for the agent's replies: **bold**, `code`, [links](url) and bare links. */
function Rich({ text }: { text: string }) {
  const parts: ReactNode[] = []
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s)]+)/g
  let last = 0
  for (let m = re.exec(text); m; m = re.exec(text)) {
    parts.push(text.slice(last, m.index))
    if (m[1]) parts.push(<b key={m.index}>{m[1]}</b>)
    else if (m[2])
      parts.push(
        <code key={m.index} className="rounded bg-neutral-200/70 px-1 text-[12.5px]">
          {m[2]}
        </code>,
      )
    else
      parts.push(
        <a key={m.index} href={m[4] ?? m[5]} target="_blank" rel="noreferrer" className="text-blue-700 underline-offset-2 hover:underline">
          {m[3] ?? m[5]}
        </a>,
      )
    last = m.index + m[0].length
  }
  parts.push(text.slice(last))
  return <>{parts}</>
}

const Avatar = ({ name, size = 'size-7' }: { name: string; size?: string }) => (
  <span className={`flex ${size} shrink-0 items-center justify-center rounded-full bg-neutral-900 text-[12px] font-bold text-white`}>{name.slice(0, 1)}</span>
)

const Spinner = () => <span className="size-3 shrink-0 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-900" />

/** M5: "작업 N단계 · 4초", folded; opens to the list of steps. */
function Steps({ tools, ms, finished }: { tools: ToolEvent[]; ms: number | null; finished: boolean }) {
  const [open, setOpen] = useState(false)
  const failed = tools.some((t) => t.status === 'error')
  const busy = !finished && tools.some((t) => t.status === 'running')
  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex h-8 items-center gap-1.5 self-start rounded-full border border-neutral-200 bg-white px-2.5 text-[12px] text-neutral-700 hover:bg-neutral-50"
      >
        {busy ? (
          <Spinner />
        ) : (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={failed ? '#b45309' : '#15803d'} strokeWidth="3" aria-hidden="true">
            <path d="M5 12l5 5 9-10" />
          </svg>
        )}
        작업 {tools.length}단계{finished && ms != null ? ` · ${seconds(ms)}` : ''}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
          <path d={open ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'} />
        </svg>
      </button>
      {open && (
        <ol className="ml-2.5 flex flex-col gap-1 border-l-2 border-neutral-200 py-1 pl-3 text-[12px] text-neutral-700">
          {tools.map((t, i) => (
            <li key={t.id} className="flex min-w-0 items-center gap-1.5">
              <span className="shrink-0 text-neutral-500">{i + 1}.</span>
              <span className="shrink-0">{toolLabel(t.name)}</span>
              {toolDetail(t.input) && <span className="min-w-0 truncate text-neutral-500">— {toolDetail(t.input)}</span>}
              {t.status === 'running' && <Spinner />}
              {t.status === 'error' && <span className="shrink-0 text-amber-700">실패</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

type Act = (a: Action) => void

/** An agent-made HTML part, in a frame that can't reach the app, the network or the page around it.
 * It talks back only through Scheduler.send / link / openTodo / openMail, which become the same actions as buttons. */
function HtmlFrame({ html, act }: { html: string; act: Act }) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState(80)
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source !== frame.current?.contentWindow || !e.data || typeof e.data !== 'object') return
      const m = e.data as { scheduler?: string; h?: number; text?: string; url?: string; id?: string }
      if (m.scheduler === 'height' && typeof m.h === 'number') setHeight(Math.min(Math.max(m.h, 24), 900))
      else if (m.scheduler === 'send' && m.text) act({ kind: 'send', text: String(m.text) })
      else if (m.scheduler === 'link' && m.url) act({ kind: 'link', url: String(m.url) })
      else if (m.scheduler === 'open_todo' && m.id) act({ kind: 'open_todo', id: String(m.id) })
      else if (m.scheduler === 'open_mail' && m.id) act({ kind: 'open_mail', id: String(m.id) })
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [act])
  const doc = `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:">
<style>:root{--fg:#171717;--muted:#525252;--line:#e5e5e5;--bg:#ffffff;--accent:#1d4ed8}
html,body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.55 'Pretendard','Malgun Gothic',sans-serif}
table{border-collapse:collapse}td,th{border:1px solid var(--line);padding:4px 8px}button{font:inherit;cursor:pointer}</style>
<script>
const post = (m) => parent.postMessage(m, '*')
window.Scheduler = { send: (text) => post({ scheduler: 'send', text }), link: (url) => post({ scheduler: 'link', url }),
  openTodo: (id) => post({ scheduler: 'open_todo', id }), openMail: (id) => post({ scheduler: 'open_mail', id }) }
addEventListener('load', () => { const tell = () => post({ scheduler: 'height', h: document.documentElement.scrollHeight }); tell(); new ResizeObserver(tell).observe(document.body) })
</script></head><body>${html}</body></html>`
  // sandbox without allow-same-origin: the frame's scripts run in an opaque origin with no access to the app.
  return <iframe ref={frame} title="에이전트가 만든 카드" sandbox="allow-scripts" srcDoc={doc} style={{ height }} className="w-full rounded-lg border-0" />
}

function PartView({ part, act }: { part: Part; act: Act }) {
  switch (part.type) {
    case 'text':
      return (
        <p className="text-[13px] leading-relaxed whitespace-pre-wrap">
          <Rich text={part.text} />
        </p>
      )
    case 'fields':
      return (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12.5px]">
          {part.rows.map((r, i) => (
            <div key={i} className="contents">
              <dt className="text-neutral-600">{r.label}</dt>
              <dd className="min-w-0 break-words">{r.value}</dd>
            </div>
          ))}
        </dl>
      )
    case 'list':
      return (
        <div className="-mx-3.5 flex flex-col">
          {part.items.map((item, i) => {
            const body = (
              <>
                <span className="truncate text-[13px] font-medium">{item.text}</span>
                {item.sub && <span className="truncate text-[11.5px] text-neutral-600">{item.sub}</span>}
              </>
            )
            const row = 'flex flex-col gap-0.5 border-t border-neutral-100 px-3.5 py-2 text-left first:border-t-0'
            return item.action ? (
              <button key={i} type="button" onClick={() => act(item.action!)} className={`${row} hover:bg-neutral-50`}>
                {body}
              </button>
            ) : (
              <div key={i} className={row}>
                {body}
              </div>
            )
          })}
        </div>
      )
    case 'date': {
      const d = new Date(part.date)
      return (
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 flex-col items-center justify-center rounded-lg bg-neutral-100">
            <span className="text-[10px] text-neutral-600">{d.getMonth() + 1}월</span>
            <span className="text-base leading-none font-bold">{d.getDate()}</span>
          </span>
          <span className="text-[13px]">
            {part.label && <b className="mr-1.5">{part.label}</b>}
            {whenText(d, part.date.includes('T'))}
          </span>
        </div>
      )
    }
    case 'todo': {
      const t = part.data
      if (!t) return <p className="text-[12px] text-neutral-500">(지워진 할 일)</p>
      const due = t.due_at ? new Date(t.due_at) : null
      return (
        <div className="flex items-center gap-3">
          <span className="flex size-11 shrink-0 flex-col items-center justify-center rounded-lg bg-neutral-100">
            {due ? (
              <>
                <span className="text-[10px] text-neutral-600">{due.getMonth() + 1}월</span>
                <span className="text-base leading-none font-bold">{due.getDate()}</span>
              </>
            ) : (
              <span className="text-[10px] text-neutral-600">날짜 없음</span>
            )}
          </span>
          <span className="flex min-w-0 flex-1 flex-col">
            <span className={`truncate text-[13.5px] font-medium ${t.done ? 'text-neutral-500 line-through' : ''}`}>{t.title}</span>
            <span className="text-[12px] text-neutral-600">{due ? whenText(due, true) : '할 일'}</span>
          </span>
          <button type="button" onClick={() => act({ kind: 'open_todo', id: t.id })} className="h-8 shrink-0 rounded-md px-2 text-[12px] text-blue-700 hover:bg-blue-50">
            열기
          </button>
        </div>
      )
    }
    case 'mail': {
      const m = part.data
      if (!m) return <p className="text-[12px] text-neutral-500">(지워진 메일)</p>
      return (
        <button type="button" onClick={() => act({ kind: 'open_mail', id: m.id })} className="flex min-w-0 flex-col gap-0.5 rounded-md text-left hover:bg-neutral-50">
          <span className="truncate text-[13px] font-medium">{m.subject}</span>
          <span className="truncate text-[11.5px] text-neutral-600">
            {m.sender.replace(/\s*<[^>]*>/, '')} · {m.received_at.slice(5, 10).replace('-', '/')} · {m.account}
          </span>
        </button>
      )
    }
    case 'buttons':
      return (
        <div className="flex flex-wrap gap-2">
          {part.buttons.map((b, i) => (
            <button key={i} type="button" onClick={() => act(b.action)} className="h-9 rounded-lg border border-neutral-300 bg-white px-3 text-[12.5px] hover:bg-neutral-50">
              {b.label}
            </button>
          ))}
        </div>
      )
    case 'html':
      return <HtmlFrame html={part.html} act={act} />
  }
}

/** M2: a card the agent made (show_card), checked by the harness and the app before it got here. */
function CardView({ card, act }: { card: Card; act: Act }) {
  return (
    <div className="flex flex-col gap-2.5 overflow-hidden rounded-2xl border border-neutral-200 bg-white px-3.5 py-3">
      {card.title && <span className="text-[13px] font-bold">{card.title}</span>}
      {card.parts.map((p, i) => (
        <PartView key={i} part={p} act={act} />
      ))}
    </div>
  )
}

/** M3: a question in a fixed frame. The agent writes the words (ask_user); Claude Code's own permission
 * questions come here through the PermissionRequest hook. The buttons are always the app's own. */
function QuestionBubble({ title, detail, options, onAnswer }: { title: string; detail?: string; options: { label: string; value: unknown }[]; onAnswer: (v: unknown) => void }) {
  return (
    <div className="flex flex-col gap-2.5 rounded-2xl rounded-bl-sm border border-amber-300 bg-amber-50 px-3.5 py-3">
      <span className="text-[13.5px] font-bold text-amber-950">{title}</span>
      {detail && <span className="text-[12.5px] break-words whitespace-pre-wrap text-amber-950">{detail}</span>}
      <div className="flex flex-wrap gap-2">
        {options.map((o, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onAnswer(o.value)}
            className={`h-10 min-w-20 flex-1 rounded-lg px-3 text-[13px] ${i === 0 ? 'bg-neutral-900 font-medium text-white hover:bg-neutral-700' : 'border border-neutral-300 bg-white hover:bg-neutral-50'}`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

const Settled = ({ children }: { children: ReactNode }) => <span className="text-[11.5px] text-neutral-500">{children}</span>

function Item({ e, act, answer }: { e: ChatEvent; act: Act; answer: (id: string, value: unknown) => void }) {
  switch (e.kind) {
    case 'text':
      return (
        <div className="self-start rounded-2xl rounded-tl-sm bg-neutral-100 px-3.5 py-2.5 text-[13.5px] leading-relaxed break-words whitespace-pre-wrap">
          <Rich text={e.text} />
        </div>
      )
    case 'note':
      return <span className="text-[12px] whitespace-pre-wrap text-neutral-500">{e.text}</span>
    case 'card':
      return <CardView card={e.card} act={act} />
    case 'question':
      return e.status === 'pending' ? (
        <QuestionBubble title={e.question} detail={e.detail} options={e.options.map((o) => ({ label: o, value: o }))} onAnswer={(v) => answer(e.id, v)} />
      ) : (
        <Settled>
          {e.question} → {e.answer ?? '답하지 않음'}
        </Settled>
      )
    case 'permission': {
      const detail = toolDetail(e.input)
      if (e.status !== 'pending')
        return (
          <Settled>
            {{ allowed: '허락함', denied: '거부함', terminal: '터미널에서 묻는 중' }[e.status]} · {toolLabel(e.name)}
            {detail ? ` — ${detail}` : ''}
          </Settled>
        )
      return (
        <QuestionBubble
          title={e.name === 'TrustFolder' ? '이 폴더에서 일해도 될까요?' : `허락이 필요해요: ${toolLabel(e.name)}`}
          detail={e.name === 'TrustFolder' ? `${detail}\nClaude Code가 이 폴더의 파일을 읽고, 고치고, 실행할 수 있게 됩니다.` : detail}
          options={[
            { label: '허락', value: true },
            { label: '거부', value: false },
          ]}
          onAnswer={(v) => answer(e.id, v)}
        />
      )
    }
    default:
      return null
  }
}

/** The selected Claude Code agent: its terminal as a chat, with the terminal itself one tab away. */
export function ChatPanel({ agent, onStatus, onOpenTodo, onOpenMail }: { agent: Agent; onStatus: () => void; onOpenTodo: (id: string) => void; onOpenMail: (id: string) => void }) {
  const [events, setEvents] = useState<ChatEvent[]>([])
  const [working, setWorking] = useState(false)
  const [alive, setAlive] = useState(false)
  const [terminalQuestion, setTerminalQuestion] = useState(false)
  const [tab, setTab] = useState<'chat' | 'terminal'>('chat')
  const [draft, setDraft] = useState('')
  const [connected, setConnected] = useState(false)
  const ws = useRef<WebSocket | null>(null)
  const list = useRef<HTMLDivElement>(null)
  const stick = useRef(true) // follow new messages unless the user scrolled up to read

  useEffect(() => {
    let disposed = false
    let retries = 0
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const connect = () => {
      const socket = new WebSocket(`${proto}://${location.host}/api/agents/${agent.id}/chat`)
      ws.current = socket
      socket.onopen = () => {
        retries = 0
        setConnected(true)
      }
      socket.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.op === 'history') setEvents(msg.events)
        else if (msg.op === 'state') {
          setWorking(msg.working)
          setAlive(msg.alive)
          setTerminalQuestion(msg.terminalQuestion)
          onStatus()
        } else if (msg.op === 'event')
          setEvents((old) => {
            const i = old.findIndex((x) => x.id === msg.event.id)
            return i < 0 ? [...old, msg.event] : old.map((x, j) => (j === i ? msg.event : x))
          })
      }
      socket.onclose = (e) => {
        setConnected(false)
        if (disposed || e.code === 4404) return
        setTimeout(() => disposed || connect(), Math.min(1000 * 2 ** retries++, 10_000))
      }
    }
    connect()
    return () => {
      disposed = true
      ws.current?.close()
    }
  }, [agent.id])

  useEffect(() => {
    if (stick.current && list.current) list.current.scrollTop = list.current.scrollHeight
  }, [events, working, tab])

  const send = (msg: object) => ws.current?.readyState === WebSocket.OPEN && ws.current.send(JSON.stringify(msg))
  const say = (text: string) => {
    send({ type: 'send', text })
    stick.current = true
  }
  const act: Act = (a) => {
    if (a.kind === 'send') say(a.text)
    else if (a.kind === 'open_todo') onOpenTodo(a.id)
    else if (a.kind === 'open_mail') onOpenMail(a.id)
    else if (a.kind === 'link' && /^https?:\/\//.test(a.url)) window.open(a.url, '_blank', 'noopener')
  }
  const answer = (id: string, value: unknown) => send({ type: 'answer', id, value })
  const submit = () => {
    if (!draft.trim()) return
    say(draft)
    setDraft('')
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter is a new line. Not while a Korean syllable is being composed: that Enter commits it.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault()
      submit()
    }
  }

  const turns = toTurns(events)
  const lastTurn = turns[turns.length - 1]
  const running = lastTurn?.tools.filter((t) => t.status === 'running').pop()
  const asking = events.some((e) => (e.kind === 'permission' || e.kind === 'question') && e.status === 'pending')
  const tabClass = (on: boolean) => `h-8 rounded-md px-3 text-[12.5px] ${on ? 'bg-white font-medium text-neutral-900 shadow-sm' : 'text-neutral-600 hover:text-neutral-900'}`

  return (
    <aside className="flex min-w-0 flex-[36] flex-col overflow-hidden rounded-xl border border-neutral-200 bg-white">
      <header className="flex items-center gap-2.5 border-b border-neutral-200 px-3.5 py-2.5">
        <Avatar name={agent.name} size="size-8" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13.5px] font-bold text-neutral-900">{agent.name}</p>
          <p className="truncate text-[11px]">
            {asking ? (
              <span className="text-amber-800">답을 기다리는 중</span>
            ) : terminalQuestion ? (
              <span className="text-amber-800">터미널에서 답을 기다리는 중</span>
            ) : working ? (
              <span className="text-amber-800">작업 중</span>
            ) : alive ? (
              <span className="text-green-700">대화 중</span>
            ) : (
              <span className="text-neutral-500">대기</span>
            )}
            <span className="text-neutral-500">
              {' '}
              · {CLI_LABEL[agent.cli]} · {agent.cwd}
            </span>
          </p>
        </div>
        <div role="tablist" aria-label="보기" className="flex shrink-0 rounded-lg bg-neutral-100 p-0.5">
          <button type="button" role="tab" aria-selected={tab === 'chat'} onClick={() => setTab('chat')} className={tabClass(tab === 'chat')}>
            대화
          </button>
          <button type="button" role="tab" aria-selected={tab === 'terminal'} onClick={() => setTab('terminal')} className={tabClass(tab === 'terminal')}>
            터미널
          </button>
        </div>
      </header>

      {tab === 'terminal' ? (
        <TerminalView agentId={agent.id} onStatus={onStatus} />
      ) : (
        <>
          <div
            ref={list}
            onScroll={(e) => {
              const el = e.currentTarget
              stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
            }}
            className="flex min-h-0 flex-1 flex-col gap-3.5 overflow-y-auto px-3.5 py-4"
          >
            {events.length === 0 && <p className="m-auto text-center text-[13px] text-neutral-500">{agent.name}에게 할 일을 부탁해 보세요</p>}
            {turns.map((turn, i) => (
              <div key={turn.request?.id ?? i} className="flex flex-col gap-3.5">
                {turn.request && 'text' in turn.request && (turn.request.shown ? (
                  // A line the app typed for the user (a handed-over mail, a document request): its short form.
                  <div className="flex max-w-[80%] flex-col gap-1 self-end rounded-2xl rounded-br-sm border border-neutral-300 bg-white px-3.5 py-2.5">
                    <span className="text-[11px] font-medium text-neutral-500">{turn.request.shown.label}</span>
                    <span className="truncate text-[13px] font-medium">{turn.request.shown.title}</span>
                    {turn.request.shown.request && <span className="text-[13px] leading-relaxed whitespace-pre-wrap text-neutral-700">{turn.request.shown.request}</span>}
                  </div>
                ) : (
                  <div className="max-w-[80%] self-end rounded-2xl rounded-br-sm bg-neutral-900 px-3.5 py-2.5 text-[13.5px] leading-relaxed whitespace-pre-wrap text-white">{turn.request.text}</div>
                ))}
                {(turn.tools.length > 0 || turn.items.length > 0) && (
                  <div className="flex items-start gap-2">
                    <Avatar name={agent.name} />
                    <div className="flex min-w-0 flex-1 flex-col gap-2 pr-6">
                      {turn.tools.length > 0 && <Steps tools={turn.tools} ms={turn.ms} finished={turn.finished} />}
                      {turn.items.map((e) => (
                        <Item key={e.id} e={e} act={act} answer={answer} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
            {working && !asking && (
              <div className="flex items-center gap-2">
                <Avatar name={agent.name} />
                <span className="flex h-8 items-center gap-2 rounded-full bg-neutral-100 px-3 text-[12px] text-neutral-700">
                  <Spinner />
                  {running ? `${toolLabel(running.name)} 중` : '생각하는 중'}
                </span>
              </div>
            )}
          </div>

          {terminalQuestion && !asking && (
            <div className="mx-3 mb-1 flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-950">
              <span className="flex-1">터미널에서 답이 필요해요</span>
              <button type="button" onClick={() => setTab('terminal')} className="h-8 rounded-md border border-amber-300 bg-white px-2.5 text-[12px] hover:bg-amber-100">
                터미널 보기
              </button>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault()
              submit()
            }}
            className="flex items-end gap-2 border-t border-neutral-200 px-3 py-2.5"
          >
            <label htmlFor="chat-input" className="sr-only">
              메시지
            </label>
            <textarea
              id="chat-input"
              rows={1}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              placeholder={connected ? '메시지 입력 (Shift+Enter 줄바꿈)' : '연결하는 중…'}
              className="field-sizing-content max-h-40 min-h-11 flex-1 resize-none rounded-[22px] border border-neutral-300 px-4 py-2.5 text-[13.5px] leading-relaxed outline-none focus:border-neutral-500"
            />
            {working && !draft.trim() ? (
              <button type="button" onClick={() => send({ type: 'stop' })} aria-label="작업 중지" className="flex size-11 shrink-0 items-center justify-center rounded-full bg-neutral-900 text-white hover:bg-neutral-700">
                <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
                  <rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" />
                </svg>
              </button>
            ) : (
              <button type="submit" aria-label="보내기" disabled={!draft.trim()} className="flex size-11 shrink-0 items-center justify-center rounded-full bg-neutral-900 text-white hover:bg-neutral-700 disabled:bg-neutral-300">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              </button>
            )}
          </form>
        </>
      )}
    </aside>
  )
}

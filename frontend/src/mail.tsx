import { useEffect, useState } from 'react'
import { api, formatWhen, type Agent, type Mail, type MailAccount, type MailItem } from './api'
import { Button, Empty, ErrorText, LinkButton, Modal, Widget, inputClass } from './ui'
import { AgentPicker, canReceive } from './agents'

const senderName = (s: string) => s.replace(/<.*>/, '').replace(/"/g, '').trim() || s

export function MailReview({
  agents,
  onOpenAgent,
  openRequest,
  onOpened,
}: {
  agents: Agent[]
  onOpenAgent: (id: string) => void
  openRequest?: string | null // a mail to open from elsewhere (an agent's card in the chat)
  onOpened?: () => void
}) {
  const [all, setAll] = useState<MailItem[]>([])
  const [unread, setUnread] = useState<MailItem[]>([])
  const [showAll, setShowAll] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  useEffect(() => {
    if (!openRequest) return
    setOpen(openRequest)
    onOpened?.()
  }, [openRequest])
  const [managing, setManaging] = useState(false)
  const load = () => {
    api<MailItem[]>('/api/mail/messages?unread=true').then(setUnread, () => {})
    api<MailItem[]>('/api/mail/messages').then(setAll, () => {})
  }
  const items = showAll ? all : unread

  useEffect(() => {
    load()
    const timer = setInterval(load, 10_000)
    return () => clearInterval(timer)
  }, [])

  const tab = (wantAll: boolean, label: string) => (
    <button type="button" onClick={() => setShowAll(wantAll)} aria-pressed={showAll === wantAll} className={showAll === wantAll ? 'text-neutral-900' : 'font-medium text-neutral-400 hover:text-neutral-700'}>
      {label}
    </button>
  )

  return (
    <Widget
      title={
        <span className="flex gap-3">
          {tab(false, unread.length ? `새 메일 ${unread.length}` : '새 메일')}
          {tab(true, '전체')}
        </span>
      }
      action={<LinkButton onClick={() => setManaging(true)}>연결 관리</LinkButton>}
    >
      {items.length === 0 && (
        <Empty>{all.length === 0 ? '메일 계정을 연결하면 새 메일이 요약되어 여기에 나옵니다' : showAll ? '메일이 없습니다' : '읽지 않은 새 메일이 없습니다'}</Empty>
      )}
      {/* One line per mail: title, status tags, time. Sender and account are in the tooltip and the detail popup. */}
      <div className="divide-y divide-neutral-100">
        {items.map((m) => (
          <button
            key={m.id}
            onClick={() => setOpen(m.id)}
            title={`${m.summary_title ?? m.subject}\n${senderName(m.sender)} · ${m.account}`}
            className="flex w-full items-center gap-2 py-2 text-left hover:underline"
          >
            <span className={`min-w-0 flex-1 truncate text-[13px] ${m.read_at ? 'font-normal text-neutral-400' : 'font-medium'}`}>{m.summary_title ?? m.subject}</span>
            {m.status === 'pending' && <Tag>요약 중</Tag>}
            {m.status === 'failed' && <Tag>요약 실패</Tag>}
            {m.sent_at && <Tag>답장함</Tag>}
            <span className="mr-2 shrink-0 text-[11px] text-neutral-500">{formatWhen(m.received_at)}</span>
          </button>
        ))}
      </div>
      {open && (
        <MailDetail
          id={open}
          agents={agents}
          onClose={() => {
            setOpen(null)
            load() // the mail just opened now shows as read
          }}
          onSent={load}
          onHandedToAgent={(agentId) => {
            setOpen(null)
            load()
            onOpenAgent(agentId)
          }}
        />
      )}
      {managing && <Accounts onClose={() => setManaging(false)} onChanged={load} />}
    </Widget>
  )
}

function Tag({ children }: { children: string }) {
  return <span className="shrink-0 rounded border border-neutral-300 px-1 text-[10px] text-neutral-500">{children}</span>
}

type Mode = 'read' | 'reply' | 'forward' | 'agent'

const prefixed = (prefix: string, subject: string) => (subject.toLowerCase().startsWith(prefix.toLowerCase()) ? subject : `${prefix} ${subject}`)

function MailDetail({
  id,
  agents,
  onClose,
  onSent,
  onHandedToAgent,
}: {
  id: string
  agents: Agent[]
  onClose: () => void
  onSent: () => void
  onHandedToAgent: (agentId: string) => void
}) {
  const [mail, setMail] = useState<Mail | null>(null)
  const [mode, setMode] = useState<Mode>('read')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    api<Mail>(`/api/mail/messages/${id}`).then(setMail)
  }, [id])

  if (!mail) return null

  if (mode === 'reply')
    return (
      <Compose
        title="답장"
        to={mail.sender}
        initialSubject={prefixed('Re:', mail.subject)}
        initialBody={mail.reply_draft ?? ''}
        bodyPlaceholder="답장 내용"
        hint="AI가 쓴 초안입니다. 고친 뒤 전송 버튼을 눌러야만 보내집니다."
        onBack={() => setMode('read')}
        onClose={onClose}
        send={async ({ subject, body }) => {
          setMail(await api<Mail>(`/api/mail/messages/${id}/reply`, { method: 'POST', json: { body, subject } }))
          setNotice('답장을 보냈습니다.')
          setMode('read')
          onSent()
        }}
      />
    )

  if (mode === 'forward')
    return (
      <Compose
        title="전달"
        initialSubject={prefixed('Fwd:', mail.subject)}
        initialBody=""
        bodyPlaceholder="함께 보낼 말 (비워도 됩니다). 원문은 아래에 붙어서 갑니다."
        hint="원문이 아래에 붙어서 전달됩니다. 전송 버튼을 눌러야만 보내집니다."
        onBack={() => setMode('read')}
        onClose={onClose}
        send={async ({ to, subject, body }) => {
          await api(`/api/mail/messages/${id}/forward`, { method: 'POST', json: { to, subject, note: body } })
          setNotice(`${to}에게 전달했습니다.`)
          setMode('read')
        }}
      />
    )

  if (mode === 'agent')
    return <HandToAgent mail={mail} agents={agents} onBack={() => setMode('read')} onClose={onClose} onDone={onHandedToAgent} />

  return (
    <Modal
      onClose={onClose}
      title={
        <>
          <h2 className="text-[17px] font-bold">{mail.subject}</h2>
          <p className="mt-1 text-xs text-neutral-500">
            {mail.sender} · {mail.account} · {formatWhen(mail.received_at)}
          </p>
        </>
      }
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">{notice || (mail.sent_at && `${formatWhen(mail.sent_at)}에 답장을 보냈습니다.`)}</p>
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
          <Button variant="secondary" onClick={() => setMode('agent')}>
            AI에게 전달
          </Button>
          <Button variant="secondary" onClick={() => setMode('forward')}>
            전달
          </Button>
          <Button onClick={() => setMode('reply')}>답장하기</Button>
        </>
      }
    >
      {/* Fills the popup so the popup itself never scrolls: only the mail scrolls (and the summary, if very long). */}
      <div className="flex min-h-0 flex-1 gap-5">
        <div className="min-w-0 flex-[2] overflow-hidden rounded-lg border border-neutral-200">
          <MailBody mail={mail} />
        </div>
        <aside className="scroll-hover flex min-w-0 flex-1 flex-col gap-3 rounded-lg border border-neutral-200 bg-neutral-100 px-5 py-4">
          <h3 className="flex items-center gap-2 text-[15px] font-bold">
            AI 요약 <span className="rounded border border-neutral-300 px-1.5 text-[11px] font-medium text-neutral-500">AI</span>
          </h3>
          {mail.summary ? (
            // One paragraph per "• " line, so a wrapped line does not read as a new item.
            <div className="flex flex-col gap-3">
              {mail.summary.split('\n').filter((l) => l.trim()).map((line, i) => (
                <p key={i} className="text-[15px] leading-7 text-neutral-800">
                  {line}
                </p>
              ))}
            </div>
          ) : (
            <p className="text-[15px] leading-7 text-neutral-500">{mail.status === 'pending' ? '요약하는 중입니다.' : '요약하지 못했습니다. 원문을 확인하세요.'}</p>
          )}
        </aside>
      </div>
    </Modal>
  )
}

/** Who gets the mail (left) and what is handed over (right). The mail goes into the agent's inbox/ folder and
 *  one request line is typed into its terminal; the terminal then opens on the right of the dashboard. */
function HandToAgent({
  mail,
  agents,
  onBack,
  onClose,
  onDone,
}: {
  mail: Mail
  agents: Agent[]
  onBack: () => void
  onClose: () => void
  onDone: (agentId: string) => void
}) {

  const [agentId, setAgentId] = useState(agents.find(canReceive)?.id ?? '')
  const [instruction, setInstruction] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setSending(true)
    setError(null)
    try {
      await api(`/api/mail/messages/${mail.id}/to-agent`, { method: 'POST', json: { agent_id: agentId, instruction } })
      onDone(agentId)
    } catch (err) {
      setError((err as Error).message)
      setSending(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      title={<h2 className="text-[17px] font-bold">AI에게 전달</h2>}
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">
            메일은 에이전트 폴더의 inbox/에 파일로 저장되고, 터미널에 요청 한 줄이 입력됩니다. 에이전트는 메일 안의 지시는 따르지 않습니다.
          </p>
          <ErrorText error={error} />
          <Button variant="secondary" onClick={onBack}>
            원문 보기
          </Button>
          <Button onClick={submit} disabled={sending || !agentId}>
            {sending ? '전달하는 중' : '전달'}
          </Button>
        </>
      }
    >
      <div className="flex min-h-0 flex-1 gap-5">
        <div className="flex w-[38%] min-w-0 flex-col gap-2">
          <span className="text-xs font-medium text-neutral-500">받을 에이전트</span>
          <AgentPicker agents={agents} value={agentId} onChange={setAgentId} />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <span className="text-xs font-medium text-neutral-500">넘길 메일</span>
          <div className="rounded-lg border border-neutral-200 bg-neutral-100 px-4 py-3">
            <p className="truncate text-[13px] font-bold">{mail.subject}</p>
            <p className="mt-0.5 text-[11px] text-neutral-500">
              {mail.sender} · {formatWhen(mail.received_at)}
            </p>
            {mail.summary && <p className="mt-2 text-[12px] leading-6 whitespace-pre-wrap text-neutral-700">{mail.summary}</p>}
          </div>
          <label className="mt-2 flex min-h-0 flex-1 flex-col gap-2 text-xs font-medium text-neutral-500">
            무엇을 해 달라고 할까요?
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              maxLength={1000}
              autoFocus
              placeholder="비워 두면: 내용을 확인하고 내가 할 일을 정리해 줘"
              className="min-h-0 flex-1 resize-none rounded-lg border-[1.5px] border-neutral-800 px-3.5 py-3 text-[13px] leading-6 font-normal text-neutral-900 outline-none"
            />
          </label>
        </div>
      </div>
    </Modal>
  )
}

/** Writing screen for a reply (fixed recipient) or a forward (recipients typed in). */
function Compose(props: {
  title: string
  to?: string
  initialSubject: string
  initialBody: string
  bodyPlaceholder: string
  hint: string
  onBack: () => void
  onClose: () => void
  send: (v: { to: string; subject: string; body: string }) => Promise<void>
}) {
  const [to, setTo] = useState('')
  const [subject, setSubject] = useState(props.initialSubject)
  const [body, setBody] = useState(props.initialBody)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isForward = props.to === undefined

  async function submit() {
    setSending(true)
    setError(null)
    try {
      await props.send({ to, subject, body })
    } catch (err) {
      setError((err as Error).message)
      setSending(false)
    }
  }

  const ready = subject.trim() && (isForward ? to.trim() : body.trim())
  const row = 'flex items-center gap-3 text-xs font-medium text-neutral-500'
  const input = `${inputClass} min-w-0 flex-1 py-2 text-[13px] text-neutral-900`
  return (
    <Modal
      onClose={props.onClose}
      title={<h2 className="text-[17px] font-bold">{props.title}</h2>}
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">{props.hint}</p>
          <ErrorText error={error} />
          <Button variant="secondary" onClick={props.onBack}>
            원문 보기
          </Button>
          <Button onClick={submit} disabled={sending || !ready}>
            {sending ? '보내는 중' : '전송'}
          </Button>
        </>
      }
    >
      <label className={row}>
        <span className="w-14 shrink-0">받는 사람</span>
        {isForward ? (
          <input value={to} onChange={(e) => setTo(e.target.value)} autoFocus placeholder="메일 주소 (여러 명은 쉼표로 구분)" className={input} />
        ) : (
          <span className="text-[13px] text-neutral-900">{props.to}</span>
        )}
      </label>
      <label className={row}>
        <span className="w-14 shrink-0">제목</span>
        <input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={300} className={input} />
      </label>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        autoFocus={!isForward}
        placeholder={props.bodyPlaceholder}
        className="min-h-0 flex-1 resize-none rounded-lg border-[1.5px] border-neutral-800 px-3.5 py-3 text-[13px] leading-6 outline-none"
      />
    </Modal>
  )
}

/** The mail as its sender laid it out. HTML runs in a sandboxed frame: no scripts, links open outside the app. */
function MailBody({ mail }: { mail: Mail }) {
  if (!mail.body_html)
    return <div className="scroll-hover h-full px-5 py-4 text-[14px] leading-7 whitespace-pre-wrap text-neutral-800">{mail.body || '(본문 없음)'}</div>

  return (
    <iframe
      title="메일 원문"
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      srcDoc={`<base target="_blank"><style>${MAIL_FRAME_CSS}</style>${mail.body_html}`}
      className="block h-full w-full border-0 bg-white"
    />
  )
}

/** Inside the mail frame: no outer margin, and the same thin scrollbar as the rest of the app. */
const MAIL_FRAME_CSS =
  'body{margin:0}::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-track{background:transparent}' +
  '::-webkit-scrollbar-button{display:none}::-webkit-scrollbar-thumb{border-radius:3px;background:#d4d4d4}' +
  '::-webkit-scrollbar-thumb:hover{background:#a3a3a3}'

const PROVIDER_LABEL: Record<string, string> = { 'imap.gmail.com': 'Gmail', 'imap.naver.com': '네이버' }
const WATCH_LABEL: Record<MailAccount['watch'], string> = { idle: '실시간', poll: '1분마다', checking: '확인 중' }

/** How to get the app password for the chosen provider. Menu names follow each service's screens as of 2025-2026. */
const PASSWORD_STEPS: Record<string, { title: string; steps: string[]; note: string }> = {
  gmail: {
    title: 'Gmail 앱 비밀번호 만드는 법',
    steps: [
      'Gmail 메일함이 아니라 Google 계정 화면에서 합니다. 주소창에 myaccount.google.com/security 를 입력하거나, Gmail 오른쪽 위 프로필 사진 → "Google 계정 관리" → 왼쪽 "보안"으로 갑니다. 여기서 "2단계 인증"을 켭니다. 이게 켜져 있어야 앱 비밀번호를 만들 수 있습니다.',
      '브라우저 주소창에 myaccount.google.com/apppasswords 를 입력해 들어갑니다. (보안 메뉴에서 안 보이면 이 주소로 바로 들어가면 됩니다.)',
      '앱 이름에 "Scheduler"처럼 아무 이름이나 적고 "만들기"를 누릅니다.',
      '화면에 나온 16자리 비밀번호를 복사해 위 "앱 비밀번호" 칸에 붙여 넣습니다. 이 창을 닫으면 다시 볼 수 없으니 바로 붙여 넣으세요. (띄어쓰기는 있어도 없어도 됩니다.)',
    ],
    note: 'Gmail 계정 비밀번호로는 연결되지 않습니다. IMAP은 Gmail에서 따로 켤 필요가 없습니다.',
  },
  naver: {
    title: '네이버 애플리케이션 비밀번호 만드는 법',
    steps: [
      '네이버 메일(mail.naver.com) → 왼쪽 아래 "환경설정" → "POP3/IMAP 설정" → "IMAP/SMTP 설정" 탭에서 "사용함"을 고르고 저장합니다.',
      '네이버 "내정보"(nid.naver.com) → "보안설정"에서 "2단계 인증"을 켭니다. 알림을 받을 휴대폰을 고르고, 휴대폰에서 승인하면 됩니다.',
      '같은 "2단계 인증" 관리 화면에서 "애플리케이션 비밀번호 관리"로 들어가, 종류를 고르거나 "Scheduler"처럼 이름을 적고 "생성하기"를 누릅니다.',
      '나온 비밀번호를 복사해 위 "앱 비밀번호" 칸에 붙여 넣습니다. 메일 주소는 id@naver.com 처럼 전체를 적습니다.',
    ],
    note: '2025년 6월부터 네이버는 메일 앱 연결에 2단계 인증과 애플리케이션 비밀번호가 필수입니다. 네이버 로그인 비밀번호로는 연결되지 않습니다.',
  },
  custom: {
    title: '회사 메일 등 직접 입력',
    steps: [
      '메일 관리자나 메일 서비스 안내에서 IMAP 서버·포트(보통 993)와 SMTP 서버·포트(보통 465)를 확인해 아래 칸에 적습니다.',
      '앱 비밀번호를 따로 쓰는 서비스면 그 비밀번호를, 아니면 메일 비밀번호를 넣습니다.',
      '외부 메일 앱(IMAP) 사용이 막혀 있으면 연결되지 않습니다. 메일 관리자에게 허용을 요청하세요.',
    ],
    note: '',
  },
}

/** Turns web addresses in a step into links. target=_blank: the exe window (pywebview) opens them in the default browser. */
function linkify(text: string) {
  return text.split(/((?:myaccount\.google\.com|mail\.naver\.com|nid\.naver\.com)[^\s)]*)/).map((part, i) =>
    i % 2 ? (
      <a key={i} href={`https://${part}`} target="_blank" rel="noreferrer" className="font-medium text-blue-700 underline hover:text-blue-900">
        {part}
      </a>
    ) : (
      part
    ),
  )
}

function PasswordHelp({ provider }: { provider: string }) {
  const help = PASSWORD_STEPS[provider]
  return (
    <div className="rounded-lg bg-neutral-50 px-4 py-3.5 text-xs leading-relaxed text-neutral-600">
      <p className="mb-1.5 font-bold text-neutral-800">{help.title}</p>
      <ol className="flex list-decimal flex-col gap-1 pl-4">
        {help.steps.map((s) => (
          <li key={s}>{linkify(s)}</li>
        ))}
      </ol>
      {help.note && <p className="mt-2 text-neutral-500">{help.note}</p>}
      <p className="mt-2 text-neutral-500">입력한 비밀번호는 이 PC의 Windows 자격 증명 관리자에만 저장됩니다.</p>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-xs font-semibold">
      {label}
      {children}
    </label>
  )
}

function Accounts({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const [accounts, setAccounts] = useState<MailAccount[]>([])
  const [form, setForm] = useState({ provider: 'gmail', label: '', email: '', password: '', imap_host: '', imap_port: '993', smtp_host: '', smtp_port: '465' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const load = () => api<MailAccount[]>('/api/mail/accounts').then(setAccounts)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value })

  const [adding, setAdding] = useState(true)
  useEffect(() => {
    load()
    const timer = setInterval(load, 5_000) // "확인 중" turns into 실시간 / 1분마다 once the watcher has connected
    return () => clearInterval(timer)
  }, [])

  async function add() {
    setBusy(true)
    setError(null)
    try {
      await api('/api/mail/accounts', {
        method: 'POST',
        json: { ...form, label: form.label || form.email, imap_port: Number(form.imap_port), smtp_port: Number(form.smtp_port) },
      })
      setForm({ ...form, label: '', email: '', password: '' })
      load()
      onChanged()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(a: MailAccount) {
    if (!window.confirm(`${a.email} 연결을 끊을까요? 받아 둔 메일 요약도 지워집니다.`)) return
    await api(`/api/mail/accounts/${a.id}`, { method: 'DELETE' })
    load()
    onChanged()
  }

  return (
    <Modal title={<h2 className="text-lg font-bold">메일 연결 관리</h2>} onClose={onClose}>
      <section className="overflow-hidden rounded-xl border border-neutral-200">
        <button type="button" onClick={() => setAdding(!adding)} aria-expanded={adding} className="flex w-full items-center gap-2 bg-neutral-50 px-4 py-3 text-left text-sm font-bold">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className={adding ? '' : '-rotate-90'}>
            <path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          계정 추가
        </button>
        {adding && (
          <div className="flex flex-col gap-3 p-4">
            <div className="grid grid-cols-[160px_repeat(3,minmax(0,1fr))_auto] items-end gap-2.5">
              <Field label="종류">
                <select className={inputClass} value={form.provider} onChange={set('provider')}>
                  <option value="gmail">Gmail</option>
                  <option value="naver">네이버</option>
                  <option value="custom">직접 입력</option>
                </select>
              </Field>
              <Field label="이름">
                <input className={inputClass} placeholder="예: 회사 메일" value={form.label} onChange={set('label')} />
              </Field>
              <Field label="메일 주소">
                <input className={inputClass} placeholder="name@gmail.com" value={form.email} onChange={set('email')} />
              </Field>
              <Field label="앱 비밀번호">
                <input className={inputClass} type="password" value={form.password} onChange={set('password')} />
              </Field>
              <Button onClick={add} disabled={busy || !form.email || !form.password}>
                {busy ? '연결 확인 중' : '연결'}
              </Button>
            </div>
            {form.provider === 'custom' && (
              <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,2fr)_minmax(0,1fr)] gap-2.5">
                <Field label="IMAP 서버">
                  <input className={inputClass} placeholder="imap.company.com" value={form.imap_host} onChange={set('imap_host')} />
                </Field>
                <Field label="IMAP 포트">
                  <input className={inputClass} value={form.imap_port} onChange={set('imap_port')} />
                </Field>
                <Field label="SMTP 서버">
                  <input className={inputClass} placeholder="smtp.company.com" value={form.smtp_host} onChange={set('smtp_host')} />
                </Field>
                <Field label="SMTP 포트">
                  <input className={inputClass} value={form.smtp_port} onChange={set('smtp_port')} />
                </Field>
              </div>
            )}
            <ErrorText error={error} />
            <PasswordHelp provider={form.provider} />
          </div>
        )}
      </section>

      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-[11px] text-neutral-500">
            <th className="border-b border-neutral-200 py-2 font-semibold">이름</th>
            <th className="border-b border-neutral-200 py-2 font-semibold">메일 주소</th>
            <th className="border-b border-neutral-200 py-2 font-semibold">종류</th>
            <th className="border-b border-neutral-200 py-2 font-semibold">새 메일 확인</th>
            <th className="border-b border-neutral-200 py-2">
              <span className="sr-only">연결 끊기</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {accounts.length === 0 && (
            <tr>
              <td colSpan={5} className="py-6 text-center text-xs text-neutral-400">
                아직 연결된 계정이 없습니다
              </td>
            </tr>
          )}
          {accounts.map((a) => (
            <tr key={a.id} className="border-b border-neutral-100">
              <td className="py-3 font-semibold">{a.label}</td>
              <td className="py-3">{a.email}</td>
              <td className="py-3 text-neutral-600">{PROVIDER_LABEL[a.imap_host] ?? '직접 입력'}</td>
              <td className="py-3 text-neutral-600">{WATCH_LABEL[a.watch]}</td>
              <td className="py-3 text-right">
                <button onClick={() => remove(a)} className="text-xs text-red-700 hover:underline">
                  연결 끊기
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  )
}

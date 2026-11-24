import { useEffect, useState } from 'react'
import { api, formatWhen, type Mail, type MailAccount, type MailItem } from './api'
import { Button, Empty, ErrorText, LinkButton, Modal, Section, Widget, inputClass } from './ui'

const senderName = (s: string) => s.replace(/<.*>/, '').replace(/"/g, '').trim() || s

export function MailReview() {
  const [items, setItems] = useState<MailItem[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const [managing, setManaging] = useState(false)
  const load = () => api<MailItem[]>('/api/mail/messages').then(setItems, () => {})

  useEffect(() => {
    load()
    const timer = setInterval(load, 10_000)
    return () => clearInterval(timer)
  }, [])

  return (
    <Widget title="메일 검토" action={<LinkButton onClick={() => setManaging(true)}>연결 관리</LinkButton>}>
      {items.length === 0 && <Empty>메일 계정을 연결하면 새 메일이 요약되어 여기에 나옵니다</Empty>}
      {items.map((m) => (
        <button key={m.id} onClick={() => setOpen(m.id)} className="flex flex-col gap-0.5 rounded-md bg-neutral-100 px-3 py-2.5 text-left hover:bg-neutral-200">
          <span className="truncate text-[13px] font-medium">{m.summary_title ?? m.subject}</span>
          <span className="flex items-center gap-1.5 text-[11px] text-neutral-500">
            <span className="truncate">
              {m.account} · {senderName(m.sender)} · {formatWhen(m.received_at)}
            </span>
            {m.status === 'pending' && <Tag>요약 중</Tag>}
            {m.status === 'failed' && <Tag>요약 실패</Tag>}
            {m.sent_at && <Tag>답장함</Tag>}
          </span>
        </button>
      ))}
      {open && <MailDetail id={open} onClose={() => setOpen(null)} onSent={load} />}
      {managing && <Accounts onClose={() => setManaging(false)} onChanged={load} />}
    </Widget>
  )
}

function Tag({ children }: { children: string }) {
  return <span className="shrink-0 rounded border border-neutral-300 px-1 text-[10px] text-neutral-500">{children}</span>
}

function MailDetail({ id, onClose, onSent }: { id: string; onClose: () => void; onSent: () => void }) {
  const [mail, setMail] = useState<Mail | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<Mail>(`/api/mail/messages/${id}`).then((m) => {
      setMail(m)
      setDraft(m.reply_draft ?? '')
    })
  }, [id])

  async function send() {
    setSending(true)
    setError(null)
    try {
      setMail(await api<Mail>(`/api/mail/messages/${id}/reply`, { method: 'POST', json: { body: draft } }))
      onSent()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSending(false)
    }
  }

  if (!mail) return null
  return (
    <Modal
      onClose={onClose}
      title={
        <>
          <h2 className="text-[17px] font-bold">{mail.summary_title ?? mail.subject}</h2>
          <p className="mt-1 text-xs text-neutral-500">
            {mail.sender} · {mail.account} · {formatWhen(mail.received_at)}
          </p>
        </>
      }
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">
            {mail.sent_at ? `${formatWhen(mail.sent_at)}에 답장을 보냈습니다.` : 'AI는 메일을 보내지 않습니다. 전송 버튼을 눌러야만 보내집니다.'}
          </p>
          <ErrorText error={error} />
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
          <Button onClick={send} disabled={sending || !draft.trim()}>
            {sending ? '보내는 중' : '전송'}
          </Button>
        </>
      }
    >
      <Section title="요약" tag="AI">
        <div className="rounded-lg bg-neutral-100 px-3.5 py-3 text-[13px] whitespace-pre-wrap">
          {mail.summary ?? (mail.status === 'pending' ? '요약하는 중입니다.' : '요약하지 못했습니다. 원문을 확인하세요.')}
        </div>
      </Section>
      <Section title="원문">
        <div className="scroll-hover max-h-40 rounded-lg border border-neutral-200 px-3.5 py-3 text-xs whitespace-pre-wrap text-neutral-600">{mail.body || '(본문 없음)'}</div>
      </Section>
      <Section title="답장 초안" tag="AI 작성 · 수정 가능">
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={7} className="rounded-lg border-[1.5px] border-neutral-800 px-3.5 py-3 text-[13px] outline-none" />
      </Section>
    </Modal>
  )
}

const PROVIDER_LABEL: Record<string, string> = { 'imap.gmail.com': 'Gmail', 'imap.naver.com': '네이버' }
const WATCH_LABEL: Record<MailAccount['watch'], string> = { idle: '실시간', poll: '1분마다', checking: '확인 중' }

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
            <p className="text-xs leading-relaxed text-neutral-500">
              Gmail: 2단계 인증 → 앱 비밀번호 · 네이버: 메일 환경설정에서 IMAP/SMTP 사용 → (2단계 인증 시) 애플리케이션 비밀번호. 비밀번호는 Windows 자격 증명 관리자에 저장됩니다.
            </p>
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

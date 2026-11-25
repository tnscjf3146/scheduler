export type Subtask = { title: string; done: boolean }
export type Todo = { id: string; title: string; due_at: string | null; done: boolean; created_at: string; memo: string; subtasks: Subtask[] }
export type Agent = {
  id: string
  name: string
  role: string
  cli: 'claude' | 'codex' | 'shell'
  cwd: string
  status: 'stopped' | 'running' | 'exited'
}
export type Approval = {
  id: string
  agent_name: string
  title: string
  background: string
  decision: string
  attachments: string[]
  status: 'pending' | 'approved' | 'rejected'
  reason: string | null
  created_at: string
  decided_at: string | null
  kind: 'approval' | 'report'
  form_name: string
  fields: { label: string; value: string; long: boolean }[]
}
export type DocForm = {
  id: string
  name: string
  kind: 'approval' | 'report'
  fields: { label: string; long: boolean }[]
}
export type MailItem = {
  id: string
  sender: string
  subject: string
  received_at: string
  summary_title: string | null
  status: 'pending' | 'ready' | 'failed'
  sent_at: string | null
  read_at: string | null
  account: string
}
export type Mail = MailItem & { body: string; body_html: string | null; summary: string | null; reply_draft: string | null }
export type MailAccount = { id: string; label: string; email: string; imap_host: string; watch: 'idle' | 'poll' | 'checking' }

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.json !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: init?.json !== undefined ? JSON.stringify(init.json) : init?.body,
  })
  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail, () => null)
    throw new Error(typeof detail === 'string' ? detail : `요청 실패 (${res.status})`)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const two = (n: number) => String(n).padStart(2, '0')

/** 'YYYY-MM-DDTHH:MM' → '오늘 17:30' / '내일 13:00' / '11월 26일 10:00' */
export function formatWhen(iso: string): string {
  const d = new Date(iso)
  const today = new Date()
  const days = Math.round(
    (new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() -
      new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()) /
      86_400_000,
  )
  const time = `${two(d.getHours())}:${two(d.getMinutes())}`
  if (days === 0) return `오늘 ${time}`
  if (days === 1) return `내일 ${time}`
  if (days === -1) return `어제 ${time}`
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${time}`
}

export const dateKey = (d: Date) => `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`

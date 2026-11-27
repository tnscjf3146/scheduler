import { useEffect, useState, type ReactNode } from 'react'
import { api, formatWhen, type Agent, type Approval, type DocForm } from './api'
import { Button, Empty, ErrorText, LinkButton, Modal, Widget, inputClass } from './ui'
import { AgentPicker, canReceive } from './agents'

const KIND_LABEL = { approval: '결재', report: '보고' } as const
/** Per kind: who signs the second box, and what the two decision buttons say. */
const WORDS = {
  approval: { signer: '기안', box: '승인', yes: '승인', no: '반려' },
  report: { signer: '보고', box: '확인', yes: '확인', no: '보완 요청' },
} as const

export function Approvals({ agents, onOpenAgent }: { agents: Agent[]; onOpenAgent: (id: string) => void }) {
  const [items, setItems] = useState<Approval[]>([])
  const [open, setOpen] = useState<Approval | null>(null)
  const [forms, setForms] = useState(false)
  const [showDone, setShowDone] = useState(false) // 완료: approved approvals and confirmed reports
  const load = () => api<Approval[]>(`/api/approvals?status=${showDone ? 'approved' : 'pending'}`).then(setItems, () => {})

  useEffect(() => {
    load()
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [showDone])

  const tab = (done: boolean, label: string) => (
    <button type="button" onClick={() => setShowDone(done)} aria-pressed={showDone === done} className={showDone === done ? 'text-neutral-900' : 'font-medium text-neutral-400 hover:text-neutral-700'}>
      {label}
    </button>
  )

  return (
    <Widget
      title={
        <span className="flex gap-3">
          {tab(false, '결정 사항')}
          {tab(true, '완료')}
        </span>
      }
      action={<LinkButton onClick={() => setForms(true)}>양식</LinkButton>}
    >
      {items.length === 0 && <Empty>{showDone ? '승인하거나 확인한 문서가 없습니다' : '올라온 결재나 보고가 없습니다'}</Empty>}
      {items.map((a) => (
        <button key={a.id} onClick={() => setOpen(a)} className="flex items-center gap-2 rounded-md bg-neutral-100 px-3 py-2 text-left hover:bg-neutral-200">
          <span className="shrink-0 rounded border border-neutral-300 bg-white px-1 text-[10px] text-neutral-500">{KIND_LABEL[a.kind]}</span>
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{a.title}</span>
          <span className="shrink-0 text-[11px] text-neutral-500">
            {a.agent_name} · {formatWhen(showDone && a.decided_at ? a.decided_at : a.created_at)}
          </span>
        </button>
      ))}
      {/* the popup stays open after a decision to show the stamp; the list just drops the item */}
      {open && <ApprovalDetail doc={open} onClose={() => setOpen(null)} onDecided={load} />}
      {forms && (
        <FormsDialog
          agents={agents}
          onClose={() => setForms(false)}
          onRequested={(agentId) => {
            setForms(false)
            onOpenAgent(agentId)
          }}
        />
      )}
    </Widget>
  )
}

const docNumber = (doc: Approval) => `SCH-${doc.created_at.slice(0, 10).replaceAll('-', '')}-${doc.id.slice(0, 4).toUpperCase()}`
const stampTime = (iso: string) => iso.slice(0, 16).replace('T', ' ')
/** Documents from before forms existed carry only background/decision. */
const fieldsOf = (doc: Approval) =>
  doc.fields?.length
    ? doc.fields
    : [
        { label: '배경', value: doc.background, long: true },
        { label: '결정 사항', value: doc.decision, long: true },
      ]

/** A round seal, as stamped on a paper form. */
function Seal({ children, gray }: { children: ReactNode; gray?: boolean }) {
  return (
    <span
      className={`inline-flex size-[54px] -rotate-12 items-center justify-center rounded-full border-[2.5px] text-center text-[12px] leading-tight font-extrabold ${
        gray ? 'border-neutral-500 text-neutral-500' : 'border-red-600 text-red-600'
      }`}
    >
      {children}
    </span>
  )
}

const EmptySeal = ({ children }: { children: ReactNode }) => (
  <span className="flex size-[54px] items-center justify-center rounded-full border-2 border-dashed border-current text-[11px]">{children}</span>
)

/** One document laid out like an A4 paper form: the sign-off box in the corner, the form's fields, then 의견. */
function Paper({ doc, decisionCell, opinion }: { doc: Approval; decisionCell: ReactNode; opinion: ReactNode }) {
  const words = WORDS[doc.kind]
  const th = 'w-28 border border-neutral-400 bg-neutral-100 px-3 py-2.5 text-center align-middle text-[13px] font-semibold'
  const td = 'border border-neutral-400 px-4 py-3 align-top text-[14px] leading-7'
  const none = <span className="text-neutral-400">(없음)</span>
  return (
    <article className="mx-auto flex w-full max-w-[900px] flex-col gap-6 bg-white px-14 py-12 shadow-[0_2px_14px_rgba(0,0,0,0.12)]">
      <div className="flex items-end justify-between">
        <span className="text-[11px] text-neutral-400">{docNumber(doc)}</span>
        <table className="border-collapse text-center text-[12px]">
          <thead>
            <tr>
              <th className="w-24 border border-neutral-500 bg-neutral-100 py-1 font-semibold">{words.signer}</th>
              <th className="w-24 border border-neutral-500 bg-neutral-100 py-1 font-semibold">{words.box}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="h-[78px] border border-neutral-500">
                <Seal>{doc.agent_name.replace(/\s/g, '').slice(0, 4)}</Seal>
              </td>
              <td className="h-[78px] border border-neutral-500 p-0">{decisionCell}</td>
            </tr>
            <tr>
              <td className="border border-neutral-500 py-0.5 text-[10px] text-neutral-500">{stampTime(doc.created_at).slice(5)}</td>
              <td className="border border-neutral-500 py-0.5 text-[10px] text-neutral-500">{doc.decided_at ? stampTime(doc.decided_at).slice(5) : ''}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h1 className="text-center text-[30px] font-bold tracking-[0.4em]">{doc.form_name.length <= 4 ? doc.form_name.split('').join(' ') : doc.form_name}</h1>

      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col className="w-28" />
          <col />
          <col className="w-28" />
          <col />
        </colgroup>
        <tbody>
          <tr>
            <th className={th}>제목</th>
            <td className={`${td} font-semibold`} colSpan={3}>
              {doc.title}
            </td>
          </tr>
          <tr>
            <th className={th}>{words.signer}자</th>
            <td className={td}>{doc.agent_name}</td>
            <th className={th}>{words.signer}일</th>
            <td className={td}>{stampTime(doc.created_at)}</td>
          </tr>
          {fieldsOf(doc).map((f) => (
            <tr key={f.label}>
              <th className={th}>{f.label}</th>
              <td className={`${td} whitespace-pre-wrap ${f.long ? 'h-40' : ''}`} colSpan={3}>
                {f.value || none}
              </td>
            </tr>
          ))}
          <tr>
            <th className={th}>첨부</th>
            <td className={td} colSpan={3}>
              {doc.attachments.length ? doc.attachments.map((f) => <div key={f}>{f}</div>) : none}
            </td>
          </tr>
          <tr>
            <th className={th}>의견</th>
            <td className={`${td} h-40 p-0`} colSpan={3}>
              {opinion}
            </td>
          </tr>
        </tbody>
      </table>
    </article>
  )
}

/** Gray desk the paper lies on, filling the popup body. */
const Desk = ({ children }: { children: ReactNode }) => <div className="-mx-6 -mb-5 flex-1 bg-neutral-200/70 px-6 py-6">{children}</div>

/** Clicking the empty sign-off box stamps it, which approves (or, for a report, confirms). The other way needs 의견. */
function ApprovalDetail({ doc: initial, onClose, onDecided }: { doc: Approval; onClose: () => void; onDecided: () => void }) {
  const [doc, setDoc] = useState(initial)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pending = doc.status === 'pending'
  const words = WORDS[doc.kind]

  async function decide(decision: 'approved' | 'rejected') {
    if (!pending || busy) return
    if (decision === 'rejected' && !reason.trim()) return setError(`${words.no}하려면 의견란에 사유를 적어 주세요`)
    setBusy(true)
    setError(null)
    try {
      setDoc(await api<Approval>(`/api/approvals/${doc.id}/decision`, { method: 'POST', json: { decision, reason } }))
      onDecided()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      title={<p className="text-[11px] font-medium text-neutral-500">{KIND_LABEL[doc.kind]} 문서 · {doc.form_name}</p>}
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">
            {pending
              ? `${words.box} 칸이나 ${words.yes} 버튼을 누르면 ${words.yes}됩니다. 결과와 의견은 문서를 올린 에이전트에게 전달됩니다.`
              : `${doc.status === 'approved' ? words.yes : words.no}했습니다. 결과가 ${doc.agent_name}에게 전달됩니다.`}
          </p>
          <ErrorText error={error} />
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
          {pending && (
            <>
              <Button variant="secondary" onClick={() => decide('rejected')} disabled={busy}>
                {words.no}
              </Button>
              <Button onClick={() => decide('approved')} disabled={busy}>
                {words.yes}
              </Button>
            </>
          )}
        </>
      }
    >
      <Desk>
        <Paper
          doc={doc}
          decisionCell={
            pending ? (
              <button
                onClick={() => decide('approved')}
                disabled={busy}
                title={`눌러서 ${words.yes}`}
                className="flex h-[78px] w-full items-center justify-center text-neutral-400 hover:bg-red-50 hover:text-red-600"
              >
                <EmptySeal>{busy ? '…' : words.yes}</EmptySeal>
              </button>
            ) : (
              <Seal gray={doc.status !== 'approved'}>{doc.status === 'approved' ? words.yes : words.no}</Seal>
            )
          }
          opinion={
            pending ? (
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={`의견을 적어 주세요. ${words.no}할 때는 사유가 꼭 필요합니다.`}
                className="block min-h-40 w-full resize-none px-4 py-3 text-[14px] leading-7 outline-none placeholder:text-neutral-400"
              />
            ) : (
              <div className="px-4 py-3 whitespace-pre-wrap">{doc.reason || <span className="text-neutral-400">(없음)</span>}</div>
            )
          }
        />
      </Desk>
    </Modal>
  )
}

// ---- Forms: the user edits them here, and can ask an agent to write a document in one -------------------

type Draft = Omit<DocForm, 'id'> & { id: string | null }
const blank = (): Draft => ({ id: null, name: '', kind: 'approval', fields: [{ label: '', long: true }] })

function FormsDialog({ agents, onClose, onRequested }: { agents: Agent[]; onClose: () => void; onRequested: (agentId: string) => void }) {
  const [forms, setForms] = useState<DocForm[]>([])
  const [draft, setDraft] = useState<Draft | null>(null)
  const [saved, setSaved] = useState('') // the draft as last saved, to tell unsaved changes apart
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pick = (f: Draft) => {
    setDraft(f)
    setSaved(JSON.stringify(f))
    setError(null)
  }
  const load = (selectId?: string) =>
    api<DocForm[]>('/api/forms').then((list) => {
      setForms(list)
      const next = list.find((f) => f.id === selectId) ?? list[0]
      if (next) pick(next)
      else pick(blank())
    })

  useEffect(() => {
    load().catch((err) => setError((err as Error).message))
  }, [])

  if (draft && asking && draft.id) return <RequestDocument form={draft as DocForm} agents={agents} onBack={() => setAsking(false)} onClose={onClose} onDone={onRequested} />

  const dirty = draft !== null && JSON.stringify(draft) !== saved
  const set = (patch: Partial<Draft>) => draft && setDraft({ ...draft, ...patch })
  const setField = (i: number, patch: Partial<Draft['fields'][number]>) => draft && set({ fields: draft.fields.map((f, j) => (j === i ? { ...f, ...patch } : f)) })
  const move = (i: number, d: number) => {
    if (!draft) return
    const fields = [...draft.fields]
    ;[fields[i], fields[i + d]] = [fields[i + d], fields[i]]
    set({ fields })
  }

  async function save() {
    if (!draft) return
    setError(null)
    try {
      const body = { name: draft.name, kind: draft.kind, fields: draft.fields }
      const f = await api<DocForm>(draft.id ? `/api/forms/${draft.id}` : '/api/forms', { method: draft.id ? 'PUT' : 'POST', json: body })
      await load(f.id)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  async function remove() {
    if (!draft?.id) return
    await api(`/api/forms/${draft.id}`, { method: 'DELETE' })
    await load()
  }

  // What a document in this form will look like, with empty fields.
  const preview: Approval | null = draft && {
    id: draft.id ?? '0000',
    agent_name: '에이전트',
    title: '(에이전트가 쓰는 제목)',
    background: '',
    decision: '',
    attachments: [],
    status: 'pending',
    reason: null,
    created_at: new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString(), // local time, like the server's
    decided_at: null,
    kind: draft.kind,
    form_name: draft.name || '양식 이름',
    fields: draft.fields.map((f) => ({ ...f, label: f.label || '칸 이름', value: '' })),
  }

  return (
    <Modal
      onClose={onClose}
      title={<h2 className="text-[17px] font-bold">문서 양식</h2>}
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">에이전트는 결재나 보고를 올릴 때 이 양식의 칸에 맞춰 씁니다. 이미 올라온 문서는 바뀌지 않습니다.</p>
          <ErrorText error={error} />
          {draft?.id && (
            <Button variant="secondary" onClick={remove}>
              삭제
            </Button>
          )}
          <Button variant="secondary" onClick={save} disabled={!draft || !dirty}>
            저장
          </Button>
          <Button onClick={() => setAsking(true)} disabled={!draft?.id || dirty} title={dirty ? '먼저 저장하세요' : undefined}>
            이 양식으로 AI에게 작성 요청
          </Button>
        </>
      }
    >
      <div className="flex min-h-0 flex-1 gap-5">
        <nav className="flex w-44 shrink-0 flex-col gap-1">
          {forms.map((f) => (
            <button
              key={f.id}
              onClick={() => pick(f)}
              className={`flex items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] ${draft?.id === f.id ? 'bg-neutral-800 text-white' : 'hover:bg-neutral-100'}`}
            >
              <span className="min-w-0 flex-1 truncate">{f.name}</span>
              <span className="text-[10px] opacity-60">{KIND_LABEL[f.kind]}</span>
            </button>
          ))}
          <button onClick={() => pick(blank())} className="rounded-md border border-dashed border-neutral-300 px-3 py-2 text-left text-[13px] text-neutral-500 hover:bg-neutral-50">
            + 새 양식
          </button>
        </nav>

        {draft && (
          <div className="flex w-80 shrink-0 flex-col gap-3">
            <label className="flex flex-col gap-1 text-xs font-medium text-neutral-500">
              양식 이름
              <input className={`${inputClass} text-[13px] text-neutral-900`} value={draft.name} maxLength={20} placeholder="예: 주간 보고서" onChange={(e) => set({ name: e.target.value })} />
            </label>
            <div className="flex flex-col gap-1 text-xs font-medium text-neutral-500">
              종류
              <div className="flex gap-1">
                {(['approval', 'report'] as const).map((k) => (
                  <button
                    key={k}
                    onClick={() => set({ kind: k })}
                    className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${draft.kind === k ? 'border-neutral-800 bg-neutral-800 text-white' : 'border-neutral-300 text-neutral-700'}`}
                  >
                    {k === 'approval' ? '결재 · 승인/반려' : '보고 · 확인/보완 요청'}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex min-h-0 flex-col gap-1.5 text-xs font-medium text-neutral-500">
              칸 (제목 · 기안자 · 첨부 · 의견은 항상 들어갑니다)
              {draft.fields.map((f, i) => (
                <div key={i} className="flex items-center gap-1">
                  <input className={`${inputClass} min-w-0 flex-1 text-[13px] text-neutral-900`} value={f.label} maxLength={20} placeholder="칸 이름" onChange={(e) => setField(i, { label: e.target.value })} />
                  <label className="flex shrink-0 items-center gap-1 px-1 font-normal text-neutral-600" title="넓은 칸으로">
                    <input type="checkbox" checked={f.long} onChange={(e) => setField(i, { long: e.target.checked })} />
                    넓게
                  </label>
                  <LinkButton onClick={() => move(i, -1)} disabled={i === 0} aria-label="위로">
                    ↑
                  </LinkButton>
                  <LinkButton onClick={() => move(i, 1)} disabled={i === draft.fields.length - 1} aria-label="아래로">
                    ↓
                  </LinkButton>
                  <LinkButton onClick={() => set({ fields: draft.fields.filter((_, j) => j !== i) })} disabled={draft.fields.length === 1} aria-label="칸 삭제">
                    ✕
                  </LinkButton>
                </div>
              ))}
              {draft.fields.length < 12 && (
                <button onClick={() => set({ fields: [...draft.fields, { label: '', long: true }] })} className="self-start text-xs text-neutral-500 hover:text-neutral-900">
                  + 칸 추가
                </button>
              )}
            </div>
          </div>
        )}

        {preview && (
          <div className="scroll-hover min-w-0 flex-1 overflow-auto rounded-lg bg-neutral-200/70 p-5">
            <Paper doc={preview} decisionCell={<span className="flex h-[78px] items-center justify-center text-neutral-300"><EmptySeal>{WORDS[preview.kind].yes}</EmptySeal></span>} opinion={null} />
          </div>
        )}
      </div>
    </Modal>
  )
}

/** Types a request into an agent's terminal: write a document in this form and submit it. */
function RequestDocument({ form, agents, onBack, onClose, onDone }: { form: DocForm; agents: Agent[]; onBack: () => void; onClose: () => void; onDone: (agentId: string) => void }) {
  const [agentId, setAgentId] = useState(agents.find(canReceive)?.id ?? '')
  const [instruction, setInstruction] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setSending(true)
    setError(null)
    try {
      await api(`/api/forms/${form.id}/request`, { method: 'POST', json: { agent_id: agentId, instruction } })
      onDone(agentId)
    } catch (err) {
      setError((err as Error).message)
      setSending(false)
    }
  }

  return (
    <Modal
      onClose={onClose}
      title={<h2 className="text-[17px] font-bold">AI에게 문서 작성 요청</h2>}
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">에이전트 터미널에 요청 한 줄이 입력됩니다. 에이전트가 양식에 맞춰 쓴 문서는 결정 사항 위젯에 올라옵니다.</p>
          <ErrorText error={error} />
          <Button variant="secondary" onClick={onBack}>
            양식으로
          </Button>
          <Button onClick={submit} disabled={sending || !agentId || !instruction.trim()}>
            {sending ? '보내는 중' : '요청 보내기'}
          </Button>
        </>
      }
    >
      <div className="flex min-h-0 flex-1 gap-5">
        <div className="flex w-[38%] min-w-0 flex-col gap-2">
          <span className="text-xs font-medium text-neutral-500">쓸 에이전트</span>
          <AgentPicker agents={agents} value={agentId} onChange={setAgentId} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <span className="text-xs font-medium text-neutral-500">양식</span>
          <div className="rounded-lg border border-neutral-200 bg-neutral-100 px-4 py-3">
            <p className="text-[13px] font-bold">
              {form.name} <span className="font-normal text-neutral-500">· {KIND_LABEL[form.kind]}</span>
            </p>
            <p className="mt-1 text-[12px] text-neutral-600">칸: {form.fields.map((f) => f.label).join(', ')}</p>
          </div>
          <label className="mt-2 flex min-h-0 flex-1 flex-col gap-2 text-xs font-medium text-neutral-500">
            무엇에 대해 써 달라고 할까요?
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              maxLength={1000}
              autoFocus
              placeholder="예: 이번 주에 한 작업을 정리해서 보고해 줘"
              className="min-h-0 flex-1 resize-none rounded-lg border-[1.5px] border-neutral-800 px-3.5 py-3 text-[13px] leading-6 font-normal text-neutral-900 outline-none"
            />
          </label>
        </div>
      </div>
    </Modal>
  )
}

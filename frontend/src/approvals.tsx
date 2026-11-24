import { useEffect, useState } from 'react'
import { api, formatWhen, type Approval } from './api'
import { Button, Empty, ErrorText, Modal, Section, Widget, inputClass } from './ui'

export function Approvals() {
  const [items, setItems] = useState<Approval[]>([])
  const [open, setOpen] = useState<Approval | null>(null)
  const load = () => api<Approval[]>('/api/approvals?status=pending').then(setItems, () => {})

  useEffect(() => {
    load()
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [])

  return (
    <Widget title="결재 대기">
      {items.length === 0 && <Empty>대기 중인 결재가 없습니다</Empty>}
      {items.map((a) => (
        <button key={a.id} onClick={() => setOpen(a)} className="flex items-center gap-2 rounded-md bg-neutral-100 px-3 py-2 text-left hover:bg-neutral-200">
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{a.title}</span>
          <span className="shrink-0 text-[11px] text-neutral-500">
            {a.agent_name} · {formatWhen(a.created_at)}
          </span>
        </button>
      ))}
      {open && (
        <ApprovalDetail
          doc={open}
          onClose={() => setOpen(null)}
          onDecided={() => {
            setOpen(null)
            load()
          }}
        />
      )}
    </Widget>
  )
}

function ApprovalDetail({ doc, onClose, onDecided }: { doc: Approval; onClose: () => void; onDecided: () => void }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function decide(decision: 'approved' | 'rejected') {
    try {
      await api(`/api/approvals/${doc.id}/decision`, { method: 'POST', json: { decision, reason } })
      onDecided()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <Modal
      onClose={onClose}
      title={
        <>
          <p className="flex items-center gap-1.5 text-[11px] font-medium text-neutral-500">
            결재 문서 <span className="rounded border border-neutral-300 px-1 text-[10px]">대기</span>
          </p>
          <h2 className="mt-1 text-[17px] font-bold">{doc.title}</h2>
        </>
      }
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">결과는 문서를 올린 에이전트에게 전달됩니다.</p>
          <ErrorText error={error} />
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
          <Button variant="secondary" onClick={() => decide('rejected')}>
            반려
          </Button>
          <Button onClick={() => decide('approved')}>승인</Button>
        </>
      }
    >
      <table className="overflow-hidden rounded-md text-xs outline outline-neutral-200">
        <tbody>
          {[
            ['올린 에이전트', doc.agent_name],
            ['올린 시각', formatWhen(doc.created_at)],
            ['결재자', '나'],
          ].map(([k, v]) => (
            <tr key={k} className="border-b border-neutral-200 last:border-0">
              <th className="w-36 bg-neutral-100 px-3 py-2 text-left font-medium text-neutral-500">{k}</th>
              <td className="px-3 py-2">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {doc.background && (
        <Section title="배경">
          <div className="rounded-lg bg-neutral-100 px-3.5 py-3 text-[13px] whitespace-pre-wrap">{doc.background}</div>
        </Section>
      )}
      <Section title="결정할 사항">
        <div className="rounded-lg bg-neutral-100 px-3.5 py-3 text-[13px] font-medium whitespace-pre-wrap">{doc.decision}</div>
      </Section>
      {doc.attachments.length > 0 && (
        <Section title="첨부">
          {doc.attachments.map((f) => (
            <div key={f} className="truncate rounded-lg border border-neutral-200 px-3.5 py-2 text-xs">
              {f}
            </div>
          ))}
        </Section>
      )}
      <Section title="반려 사유 (반려할 때만)">
        <textarea className={`${inputClass} text-[13px]`} rows={3} placeholder="반려 사유를 입력하세요" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Section>
    </Modal>
  )
}

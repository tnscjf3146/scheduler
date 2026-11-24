import { useState } from 'react'
import { api, type Agent } from './api'
import { Button, Empty, ErrorText, LinkButton, Modal, Widget, inputClass } from './ui'

// Injected by the exe window (backend/desktop.py JsApi); absent in a dev browser.
declare global {
  interface Window {
    pywebview?: { api: { pick_folder: () => Promise<string | null> } }
  }
}

export const CLI_LABEL: Record<Agent['cli'], string> = { claude: 'Claude Code', codex: 'Codex', shell: 'PowerShell' }
const STATUS_LABEL: Record<Agent['status'], string> = { running: '실행 중', stopped: '대기', exited: '종료됨' }

export function Agents({
  agents,
  selected,
  onSelect,
  onRestarted,
  reload,
}: {
  agents: Agent[]
  selected: string | null
  onSelect: (id: string) => void
  onRestarted: () => void
  reload: () => void
}) {
  // null: closed. {}: add a new agent. { from }: hand `from`'s work folder over to a new agent.
  const [adding, setAdding] = useState<{ from?: Agent } | null>(null)
  const [menu, setMenu] = useState<string | null>(null)

  async function act(agent: Agent, action: 'restart' | 'fire' | 'delete') {
    setMenu(null)
    if (action === 'restart') {
      await api(`/api/agents/${agent.id}/restart`, { method: 'POST' })
      onSelect(agent.id)
      onRestarted()
      return reload()
    }
    const ownFolder = /\\Scheduler\\agents\\/.test(agent.cwd) // the app made it; a folder the user chose is never deleted
    const question =
      action === 'fire'
        ? `'${agent.name}'을(를) 해고할까요?\n터미널 세션이 종료되고 작업 폴더는 그대로 남습니다.\n${agent.cwd}`
        : ownFolder
          ? `'${agent.name}'을(를) 삭제할까요?\n작업 폴더와 그 안의 파일까지 모두 지웁니다. 되돌릴 수 없습니다.\n${agent.cwd}`
          : `'${agent.name}'을(를) 삭제할까요?\n직접 지정한 작업 폴더는 지우지 않습니다.\n${agent.cwd}`
    if (!window.confirm(question)) return
    try {
      await api(`/api/agents/${agent.id}${action === 'delete' ? '?purge=true' : ''}`, { method: 'DELETE' })
    } catch (err) {
      window.alert((err as Error).message)
    }
    reload()
  }

  return (
    <Widget title="Agent" action={<LinkButton onClick={() => setAdding({})}>+ 추가</LinkButton>}>
      {agents.length === 0 && <Empty>에이전트를 추가하세요</Empty>}
      {agents.map((a) => (
        <div
          key={a.id}
          onClick={() => onSelect(a.id)}
          className={`relative flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 ${a.id === selected ? 'bg-neutral-800 text-white' : 'bg-neutral-100 hover:bg-neutral-200'}`}
        >
          <span className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${a.id === selected ? 'bg-neutral-600' : 'bg-neutral-300 text-neutral-700'}`}>
            {a.name.slice(0, 1)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium">{a.name}</p>
            <p className={`truncate text-[11px] ${a.id === selected ? 'text-neutral-300' : 'text-neutral-500'}`}>
              {[a.role, CLI_LABEL[a.cli], STATUS_LABEL[a.status]].filter(Boolean).join(' · ')}
            </p>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              setMenu(menu === a.id ? null : a.id)
            }}
            className="px-1 text-sm opacity-60 hover:opacity-100"
            aria-label="메뉴"
          >
            ⋯
          </button>
          {menu === a.id && (
            <div className="absolute top-full right-2 z-10 mt-1 flex w-28 flex-col rounded-md border border-neutral-200 bg-white py-1 text-xs text-neutral-900 shadow-md" onClick={(e) => e.stopPropagation()}>
              <button className="px-3 py-1.5 text-left hover:bg-neutral-100" onClick={() => act(a, 'restart')}>
                재시작
              </button>
              <button
                className="px-3 py-1.5 text-left hover:bg-neutral-100"
                onClick={() => {
                  setMenu(null)
                  setAdding({ from: a })
                }}
                title="해고하고, 같은 작업 폴더로 새 에이전트를 만듭니다"
              >
                인수인계
              </button>
              <button className="px-3 py-1.5 text-left hover:bg-neutral-100" onClick={() => act(a, 'fire')} title="작업 폴더는 남깁니다">
                해고
              </button>
              <button className="px-3 py-1.5 text-left text-red-600 hover:bg-neutral-100" onClick={() => act(a, 'delete')} title="작업 폴더까지 지웁니다">
                삭제
              </button>
            </div>
          )}
        </div>
      ))}
      {adding && (
        <AddAgent
          from={adding.from}
          onClose={() => setAdding(null)}
          onAdded={(a) => {
            setAdding(null)
            reload()
            onSelect(a.id)
          }}
        />
      )}
    </Widget>
  )
}

function AddAgent({ from, onClose, onAdded }: { from?: Agent; onClose: () => void; onAdded: (a: Agent) => void }) {
  const [form, setForm] = useState({ name: '', role: '', persona: '', cli: from?.cli ?? ('claude' as Agent['cli']), cwd: '' })
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value })

  async function pickFolder() {
    const path = await window.pywebview?.api.pick_folder()
    if (path) setForm((f) => ({ ...f, cwd: path }))
  }

  async function submit() {
    try {
      const url = from ? `/api/agents/${from.id}/handover` : '/api/agents'
      onAdded(await api<Agent>(url, { method: 'POST', json: { ...form, cwd: form.cwd.trim() || null } }))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <Modal
      title={<h2 className="text-[17px] font-bold">{from ? `인수인계: '${from.name}'의 후임` : '에이전트 추가'}</h2>}
      onClose={onClose}
      footer={
        <>
          <ErrorText error={error} />
          <span className="flex-1" />
          <Button variant="secondary" onClick={onClose}>
            취소
          </Button>
          <Button onClick={submit} disabled={!form.name.trim()}>
            {from ? '인수인계' : '추가'}
          </Button>
        </>
      }
    >
      <label className="flex flex-col gap-1 text-xs font-medium">
        이름
        <input className={inputClass} value={form.name} onChange={set('name')} placeholder="예: 코딩 담당" autoFocus />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium">
        역할
        <input className={inputClass} value={form.role} onChange={set('role')} placeholder="예: 백엔드 API 작성" />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium">
        성격과 일하는 방식
        <textarea
          className={`${inputClass} h-24 resize-y`}
          value={form.persona}
          onChange={set('persona')}
          placeholder={'예: 말이 짧고 결론부터 말한다. 확실하지 않으면 추측하지 않고 묻는다.'}
        />
        <span className="text-[11px] font-normal text-neutral-500">작업 폴더의 AGENTS.md에 들어갑니다. 나중엔 그 파일을 직접 고치면 됩니다.</span>
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium">
        CLI
        <select className={inputClass} value={form.cli} onChange={set('cli')}>
          <option value="claude">Claude Code</option>
          <option value="codex">Codex</option>
          <option value="shell">PowerShell (CLI 없이)</option>
        </select>
      </label>
      {from ? (
        <p className="rounded-md bg-neutral-100 px-3 py-2 text-[11px] text-neutral-600">
          '{from.name}'은(는) 해고되고, 새 에이전트가 같은 작업 폴더에서 새 대화로 시작합니다. 폴더의 파일은 그대로이고 AGENTS.md만 새로 씁니다.
          <br />
          <span className="break-all text-neutral-500">{from.cwd}</span>
        </p>
      ) : (
      <label className="flex flex-col gap-1 text-xs font-medium">
        작업 폴더
        <div className="flex gap-2">
          <input className={`${inputClass} flex-1`} value={form.cwd} onChange={set('cwd')} placeholder="비우면 에이전트 전용 폴더를 만듭니다" />
          {window.pywebview && (
            <Button variant="secondary" onClick={pickFolder}>
              찾아보기
            </Button>
          )}
        </div>
      </label>
      )}
      <p className="text-[11px] text-neutral-500">CLI 로그인은 터미널에서 처음 실행될 때 CLI가 직접 안내합니다.</p>
    </Modal>
  )
}

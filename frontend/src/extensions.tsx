import { useEffect, useState } from 'react'
import { api, type Agent, type Extension, type SkillSet } from './api'
import { Button, Empty, ErrorText, Modal, inputClass } from './ui'

export const KIND_LABEL = { skill: '스킬', hook: '하네스' } as const
/** Claude Code hook events, in the words the user sees. */
const EVENTS: Record<string, string> = {
  PreToolUse: '도구 실행 전',
  PostToolUse: '도구 실행 후',
  UserPromptSubmit: '요청을 보낼 때',
  Stop: '응답을 마쳤을 때',
  SessionStart: '세션 시작',
  SessionEnd: '세션 종료',
  Notification: '알림이 뜰 때',
  SubagentStop: '서브에이전트가 끝났을 때',
  PreCompact: '대화 요약 전',
}
const TOOL_EVENTS = ['PreToolUse', 'PostToolUse']
const eventLabel = (e: string) => EVENTS[e] ?? e
/** Skills and harness reach an agent as a Claude Code plugin; Codex has no such mechanism. */
export const takesExtensions = (a: Agent) => a.cli === 'claude'

/** Every agent that gets it: attached one by one or through a set. */
const usedBy = (x: Extension) => [...new Set([...x.agent_ids, ...x.via_sets])]

type Draft = Omit<Extension, 'id' | 'created_by' | 'created_at' | 'agent_ids' | 'via_sets' | 'builtin'>
const blank = (kind: Extension['kind']): Draft => ({ kind, name: '', description: '', body: '', event: 'PreToolUse', matcher: '', command: '' })
const draftOf = ({ kind, name, description, body, event, matcher, command }: Draft): Draft => ({ kind, name, description, body, event, matcher, command })

/** The "스킬 & 하네스" tab of the Agent widget. */
export function ExtensionList({ agents, items, reload, editing, setEditing }: {
  agents: Agent[]
  items: Extension[]
  reload: () => void
  editing: Extension | Draft | 'import' | null
  setEditing: (e: Extension | Draft | 'import' | null) => void
}) {
  return (
    <>
      {items.length === 0 && <Empty>스킬이나 하네스를 만들거나 가져오세요</Empty>}
      {items.map((x) => (
        <button key={x.id} onClick={() => setEditing(x)} className="flex items-start gap-2.5 rounded-md bg-neutral-100 px-2.5 py-2 text-left hover:bg-neutral-200">
          <span className="mt-0.5 shrink-0 rounded border border-neutral-300 bg-white px-1 text-[10px] text-neutral-500">{KIND_LABEL[x.kind]}</span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5">
              <span className="truncate text-[13px] font-medium">{x.name}</span>
              {!!x.builtin && <span className="shrink-0 rounded bg-neutral-200 px-1 text-[10px] text-neutral-600">기본</span>}
              {x.created_by && <span className="shrink-0 rounded bg-amber-100 px-1 text-[10px] text-amber-800">{x.created_by}이(가) 만듦 · 검토 필요</span>}
            </span>
            <span className="block truncate text-[11px] text-neutral-500">
              {x.kind === 'hook' ? `${eventLabel(x.event)}${x.matcher ? ` · ${x.matcher}` : ''} · ${x.command}` : x.description}
            </span>
          </span>
          <span className="shrink-0 text-[11px] text-neutral-500">{usedBy(x).length ? `에이전트 ${usedBy(x).length}` : '미적용'}</span>
        </button>
      ))}
      {editing === 'import' && <ImportDialog onClose={() => setEditing(null)} onImported={(x) => (reload(), setEditing(x))} />}
      {editing && editing !== 'import' && (
        <ExtensionEditor
          key={'id' in editing ? editing.id : editing.kind}
          initial={editing}
          agents={agents}
          onClose={() => setEditing(null)}
          onSaved={() => (reload(), setEditing(null))}
        />
      )}
    </>
  )
}

/** Create or edit one skill / harness, and choose which agents get it. */
function ExtensionEditor({ initial, agents, onClose, onSaved }: { initial: Extension | Draft; agents: Agent[]; onClose: () => void; onSaved: () => void }) {
  const saved = 'id' in initial ? initial : null
  const [draft, setDraft] = useState<Draft>(draftOf(initial))
  const [agentIds, setAgentIds] = useState<string[]>(saved?.agent_ids ?? [])
  const [error, setError] = useState<string | null>(null)
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch })
  const skill = draft.kind === 'skill'

  async function save() {
    setError(null)
    try {
      const x = await api<Extension>(saved ? `/api/extensions/${saved.id}` : '/api/extensions', { method: saved ? 'PUT' : 'POST', json: draft })
      await api(`/api/extensions/${x.id}/agents`, { method: 'PUT', json: { agent_ids: agentIds } })
      onSaved()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  async function remove() {
    if (saved && window.confirm(`'${saved.name}'을(를) 지울까요? 붙어 있던 에이전트에서도 빠집니다.`)) {
      await api(`/api/extensions/${saved.id}`, { method: 'DELETE' })
      onSaved()
    }
  }

  const label = 'flex flex-col gap-1 text-xs font-medium text-neutral-500'
  return (
    <Modal
      onClose={onClose}
      title={
        <>
          <h2 className="text-[17px] font-bold">{saved ? `${KIND_LABEL[draft.kind]} 고치기` : `${KIND_LABEL[draft.kind]} 만들기`}</h2>
          {saved?.created_by && (
            <p className="mt-1 text-[12px] text-amber-700">에이전트 '{saved.created_by}'이(가) 만들었습니다. 내용을 확인하고 저장하면 검토 표시가 사라집니다.</p>
          )}
        </>
      }
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">Claude Code 에이전트에만 적용됩니다. 에이전트를 재시작하면 바뀐 내용이 들어갑니다.</p>
          <ErrorText error={error} />
          {saved && (
            <Button variant="secondary" onClick={remove}>
              삭제
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            취소
          </Button>
          <Button onClick={save} disabled={!draft.name.trim()}>
            저장
          </Button>
        </>
      }
    >
      <div className="flex min-h-0 flex-1 gap-6">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          {!saved && (
            <div className="flex gap-1">
              {(['skill', 'hook'] as const).map((k) => (
                <button
                  key={k}
                  onClick={() => set({ kind: k })}
                  className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${draft.kind === k ? 'border-neutral-800 bg-neutral-800 text-white' : 'border-neutral-300 text-neutral-700'}`}
                >
                  {k === 'skill' ? '스킬 · 필요할 때 읽는 지시' : '하네스 · 정해진 때 자동 실행되는 명령'}
                </button>
              ))}
            </div>
          )}
          <label className={label}>
            이름
            <input className={`${inputClass} text-[13px] text-neutral-900`} maxLength={40} value={draft.name} onChange={(e) => set({ name: e.target.value })} placeholder={skill ? '예: 문서 쓰기 규칙' : '예: 명령 실행 기록'} />
          </label>
          {skill ? (
            <>
              <label className={label}>
                언제 쓰는지
                <input className={`${inputClass} text-[13px] text-neutral-900`} maxLength={1000} value={draft.description} onChange={(e) => set({ description: e.target.value })} placeholder="예: 문서나 보고서를 쓰거나 고칠 때" />
                <span className="font-normal text-neutral-400">Claude는 이 설명을 보고 스킬을 읽을지 정합니다.</span>
              </label>
              <label className={`${label} min-h-0 flex-1`}>
                내용 (마크다운)
                <textarea
                  className="min-h-48 flex-1 resize-none rounded-md border border-neutral-300 px-3 py-2.5 font-mono text-[12px] leading-6 font-normal text-neutral-900 outline-none focus:border-neutral-600"
                  value={draft.body}
                  onChange={(e) => set({ body: e.target.value })}
                  placeholder={'# 규칙\n- 한 문장에는 한 가지만 쓴다.\n- 결론을 먼저 쓴다.'}
                />
              </label>
            </>
          ) : (
            <>
              <label className={label}>
                실행 시점
                <select className={`${inputClass} text-[13px] text-neutral-900`} value={draft.event} onChange={(e) => set({ event: e.target.value })}>
                  {[...new Set([...Object.keys(EVENTS), draft.event])].map((e) => (
                    <option key={e} value={e}>
                      {eventLabel(e)} ({e})
                    </option>
                  ))}
                </select>
              </label>
              {TOOL_EVENTS.includes(draft.event) && (
                <label className={label}>
                  대상 도구
                  <input className={`${inputClass} font-mono text-[12px] text-neutral-900`} value={draft.matcher} onChange={(e) => set({ matcher: e.target.value })} placeholder="비우면 모든 도구. 예: Bash 또는 Edit|Write" />
                </label>
              )}
              <label className={label}>
                실행할 명령
                <textarea
                  className="h-24 resize-none rounded-md border border-neutral-300 px-3 py-2 font-mono text-[12px] font-normal text-neutral-900 outline-none focus:border-neutral-600"
                  value={draft.command}
                  onChange={(e) => set({ command: e.target.value })}
                  placeholder="예: powershell -NoProfile -File C:\hooks\log.ps1"
                />
                <span className="font-normal text-neutral-400">CLI가 묻지 않고 실행합니다. 믿을 수 있는 명령만 넣으세요.</span>
              </label>
              <label className={label}>
                설명 (선택)
                <input className={`${inputClass} text-[13px] text-neutral-900`} maxLength={1000} value={draft.description} onChange={(e) => set({ description: e.target.value })} placeholder="무엇을 왜 하는지" />
              </label>
            </>
          )}
        </div>

        <div className="flex w-72 shrink-0 flex-col gap-2">
          <span className="text-xs font-medium text-neutral-500">적용할 에이전트</span>
          {agents.length === 0 && <p className="text-[12px] text-neutral-500">에이전트가 없습니다</p>}
          <div className="flex flex-col overflow-hidden rounded-lg border border-neutral-200">
            {agents.map((a) => (
              <label key={a.id} className={`flex items-center gap-2.5 border-b border-neutral-200 px-3 py-2 last:border-b-0 ${takesExtensions(a) ? 'hover:bg-neutral-50' : 'opacity-40'}`}>
                <input
                  type="checkbox"
                  disabled={!takesExtensions(a)}
                  checked={agentIds.includes(a.id)}
                  onChange={(e) => setAgentIds(e.target.checked ? [...agentIds, a.id] : agentIds.filter((i) => i !== a.id))}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px]">{a.name}</span>
                  <span className="block text-[11px] text-neutral-500">
                    {takesExtensions(a) ? 'Claude Code' : `${a.cli === 'codex' ? 'Codex' : 'PowerShell'} · 적용 안 됨`}
                    {saved?.via_sets.includes(a.id) && ' · 세트로 적용됨'}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  )
}

type Installed = Draft & { source: string }

/** Copies a skill from ~/.claude/skills or a hook from ~/.claude/settings.json into the app. */
function ImportDialog({ onClose, onImported }: { onClose: () => void; onImported: (x: Extension) => void }) {
  const [items, setItems] = useState<Installed[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<Installed[]>('/api/extensions/installed').then(setItems, (err) => setError((err as Error).message))
  }, [])

  async function take(item: Installed) {
    try {
      onImported(await api<Extension>('/api/extensions', { method: 'POST', json: draftOf(item) }))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <Modal
      onClose={onClose}
      title={<h2 className="text-[17px] font-bold">내 스킬 · 하네스 가져오기</h2>}
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">
            ~/.claude의 스킬과 하네스는 이미 모든 Claude Code 에이전트에 적용돼 있습니다. 가져오면 앱에 사본이 생겨서, 고친 뒤 원하는 에이전트에만 붙일 수 있습니다.
          </p>
          <ErrorText error={error} />
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
        </>
      }
    >
      {items === null && !error && <Empty>찾는 중…</Empty>}
      {items?.length === 0 && <Empty>~/.claude/skills와 ~/.claude/settings.json에 스킬이나 하네스가 없습니다</Empty>}
      {items?.map((x) => (
        <div key={`${x.source}:${x.name}:${x.command}`} className="flex items-center gap-3 rounded-lg border border-neutral-200 px-4 py-3">
          <span className="shrink-0 rounded border border-neutral-300 px-1 text-[10px] text-neutral-500">{KIND_LABEL[x.kind]}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium">{x.name}</span>
            <span className="block truncate text-[11px] text-neutral-500">{x.kind === 'skill' ? x.description : `${eventLabel(x.event)} · ${x.command}`}</span>
            <span className="block truncate text-[10px] text-neutral-400">{x.source}</span>
          </span>
          <Button variant="secondary" onClick={() => take(x)}>
            가져오기
          </Button>
        </div>
      ))}
    </Modal>
  )
}

/** Checkboxes in the add-agent form: skills and harness attached one by one, besides the sets. */
export function ExtensionPicker({ value, onChange, cli }: { value: string[] | null; onChange: (ids: string[]) => void; cli: Agent['cli'] }) {
  const [items, setItems] = useState<Extension[]>([])
  useEffect(() => {
    api<Extension[]>('/api/extensions').then(setItems, () => {})
  }, [])
  if (items.length === 0) return null
  const checked = value ?? []
  const on = cli === 'claude'
  return (
    <div className="flex flex-col gap-1 text-xs font-medium">
      개별 스킬 & 하네스 (세트 말고 따로 붙일 것)
      <div className={`flex flex-wrap gap-1.5 ${on ? '' : 'opacity-40'}`}>
        {items.map((x) => (
          <label key={x.id} className="flex items-center gap-1.5 rounded-md border border-neutral-300 px-2 py-1 font-normal">
            <input type="checkbox" disabled={!on} checked={checked.includes(x.id)} onChange={(e) => onChange(e.target.checked ? [...checked, x.id] : checked.filter((i) => i !== x.id))} />
            <span className="text-[10px] text-neutral-500">{KIND_LABEL[x.kind]}</span>
            {x.name}
          </label>
        ))}
      </div>
      {!on && <span className="text-[11px] font-normal text-neutral-500">Claude Code 에이전트에만 붙일 수 있습니다.</span>}
    </div>
  )
}

/** Set checkboxes in the add-agent form. Untouched (null), the app's default set is checked. */
export function SetPicker({ value, onChange, cli }: { value: string[] | null; onChange: (ids: string[]) => void; cli: Agent['cli'] }) {
  const [sets, setSets] = useState<SkillSet[]>([])
  useEffect(() => {
    api<SkillSet[]>('/api/extensions/sets').then(setSets, () => {})
  }, [])
  if (sets.length === 0) return null
  const checked = value ?? sets.filter((s) => s.builtin).map((s) => s.id)
  const on = cli === 'claude'
  return (
    <div className="flex flex-col gap-1 text-xs font-medium">
      세트
      <div className={`flex flex-wrap gap-1.5 ${on ? '' : 'opacity-40'}`}>
        {sets.map((s) => (
          <label key={s.id} title={s.description} className="flex items-center gap-1.5 rounded-md border border-neutral-300 px-2 py-1 font-normal">
            <input type="checkbox" disabled={!on} checked={checked.includes(s.id)} onChange={(e) => onChange(e.target.checked ? [...checked, s.id] : checked.filter((i) => i !== s.id))} />
            {s.name}
            <span className="text-[10px] text-neutral-500">{s.item_ids.length}개</span>
          </label>
        ))}
      </div>
    </div>
  )
}

export type SetDraft = { name: string; description: string; item_ids: string[] }
export const blankSet = (): SetDraft => ({ name: '', description: '', item_ids: [] })

/** The "세트" tab of the Agent widget. */
export function SetList({ agents, sets, exts, reload, editing, setEditing }: {
  agents: Agent[]
  sets: SkillSet[]
  exts: Extension[]
  reload: () => void
  editing: SkillSet | SetDraft | null
  setEditing: (s: SkillSet | SetDraft | null) => void
}) {
  return (
    <>
      {sets.length === 0 && <Empty>세트를 만들어 스킬과 하네스를 묶으세요</Empty>}
      {sets.map((s) => (
        <button key={s.id} onClick={() => setEditing(s)} className="flex items-start gap-2.5 rounded-md bg-neutral-100 px-2.5 py-2 text-left hover:bg-neutral-200">
          <span className="mt-0.5 shrink-0 rounded border border-neutral-300 bg-white px-1 text-[10px] text-neutral-500">세트</span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5">
              <span className="truncate text-[13px] font-medium">{s.name}</span>
              {!!s.builtin && <span className="shrink-0 rounded bg-neutral-200 px-1 text-[10px] text-neutral-600">기본</span>}
              {s.created_by && <span className="shrink-0 rounded bg-amber-100 px-1 text-[10px] text-amber-800">{s.created_by}이(가) 만듦 · 검토 필요</span>}
            </span>
            <span className="block truncate text-[11px] text-neutral-500">
              {s.item_ids.map((i) => exts.find((x) => x.id === i)?.name).filter(Boolean).join(', ') || '비어 있음'}
            </span>
          </span>
          <span className="shrink-0 text-[11px] text-neutral-500">{s.agent_ids.length ? `에이전트 ${s.agent_ids.length}` : '미적용'}</span>
        </button>
      ))}
      {editing && (
        <SetEditor
          key={'id' in editing ? editing.id : 'new'}
          initial={editing}
          agents={agents}
          exts={exts}
          onClose={() => setEditing(null)}
          onCopy={(draft) => setEditing(draft)}
          onSaved={() => (reload(), setEditing(null))}
        />
      )}
    </>
  )
}

/** Create or edit one set: its skills and harness, and which agents get it. The default set is shown, not edited. */
function SetEditor({ initial, agents, exts, onClose, onCopy, onSaved }: {
  initial: SkillSet | SetDraft
  agents: Agent[]
  exts: Extension[]
  onClose: () => void
  onCopy: (d: SetDraft) => void
  onSaved: () => void
}) {
  const saved = 'id' in initial ? initial : null
  const locked = !!saved?.builtin
  const [draft, setDraft] = useState<SetDraft>({ name: initial.name, description: initial.description, item_ids: initial.item_ids })
  const [agentIds, setAgentIds] = useState<string[]>(saved?.agent_ids ?? [])
  const [error, setError] = useState<string | null>(null)
  const toggle = (list: string[], id: string, on: boolean) => (on ? [...list, id] : list.filter((i) => i !== id))

  async function save() {
    setError(null)
    try {
      const s = locked
        ? saved!
        : await api<SkillSet>(saved ? `/api/extensions/sets/${saved.id}` : '/api/extensions/sets', { method: saved ? 'PUT' : 'POST', json: draft })
      await api(`/api/extensions/sets/${s.id}/agents`, { method: 'PUT', json: { agent_ids: agentIds } })
      onSaved()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  async function remove() {
    if (saved && window.confirm(`세트 '${saved.name}'을(를) 지울까요? 붙어 있던 에이전트에서도 빠집니다. 안의 스킬·하네스는 남습니다.`)) {
      await api(`/api/extensions/sets/${saved.id}`, { method: 'DELETE' })
      onSaved()
    }
  }

  const label = 'flex flex-col gap-1 text-xs font-medium text-neutral-500'
  const row = 'flex items-center gap-2.5 border-b border-neutral-200 px-3 py-2 last:border-b-0'
  return (
    <Modal
      onClose={onClose}
      title={
        <>
          <h2 className="text-[17px] font-bold">{locked ? '기본 세트' : saved ? '세트 고치기' : '세트 만들기'}</h2>
          {locked && <p className="mt-1 text-[12px] text-neutral-500">앱이 관리하는 세트입니다. 담긴 것을 바꾸려면 복사해서 새 세트로 만드세요. 붙일 에이전트는 고를 수 있습니다.</p>}
          {saved?.created_by && <p className="mt-1 text-[12px] text-amber-700">에이전트 '{saved.created_by}'이(가) 만들었습니다. 내용을 확인하고 저장하면 검토 표시가 사라집니다.</p>}
        </>
      }
      footer={
        <>
          <p className="flex-1 text-[11px] text-neutral-500">Claude Code 에이전트에만 적용됩니다. 세트를 고치면 쓰는 에이전트 모두 다음 재시작 때 바뀝니다.</p>
          <ErrorText error={error} />
          {saved && (
            <Button variant="secondary" onClick={() => onCopy({ name: `${saved.name} 사본`, description: saved.description, item_ids: saved.item_ids })}>
              복사
            </Button>
          )}
          {saved && !locked && (
            <Button variant="secondary" onClick={remove}>
              삭제
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            취소
          </Button>
          <Button onClick={save} disabled={!draft.name.trim()}>
            저장
          </Button>
        </>
      }
    >
      <div className="flex min-h-0 flex-1 gap-6">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <label className={label}>
            이름
            <input className={`${inputClass} text-[13px] text-neutral-900`} maxLength={40} disabled={locked} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="예: 비서" />
          </label>
          <label className={label}>
            설명
            <input className={`${inputClass} text-[13px] text-neutral-900`} maxLength={1000} disabled={locked} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="예: 메일 분류와 일정 정리를 하는 에이전트용" />
          </label>
          <span className="text-xs font-medium text-neutral-500">담을 스킬 · 하네스</span>
          <div className="scroll-hover flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-neutral-200">
            {exts.length === 0 && <p className="px-3 py-2 text-[12px] text-neutral-500">스킬이나 하네스가 없습니다</p>}
            {exts.map((x) => (
              <label key={x.id} className={`${row} ${locked ? '' : 'hover:bg-neutral-50'}`}>
                <input type="checkbox" disabled={locked} checked={draft.item_ids.includes(x.id)} onChange={(e) => setDraft({ ...draft, item_ids: toggle(draft.item_ids, x.id, e.target.checked) })} />
                <span className="shrink-0 rounded border border-neutral-300 px-1 text-[10px] text-neutral-500">{KIND_LABEL[x.kind]}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px]">{x.name}</span>
                  <span className="block truncate text-[11px] text-neutral-500">{x.kind === 'hook' ? `${eventLabel(x.event)} · ${x.command}` : x.description}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="flex w-72 shrink-0 flex-col gap-2">
          <span className="text-xs font-medium text-neutral-500">붙일 에이전트</span>
          {agents.length === 0 && <p className="text-[12px] text-neutral-500">에이전트가 없습니다</p>}
          <div className="flex flex-col overflow-hidden rounded-lg border border-neutral-200">
            {agents.map((a) => (
              <label key={a.id} className={`${row} ${takesExtensions(a) ? 'hover:bg-neutral-50' : 'opacity-40'}`}>
                <input type="checkbox" disabled={!takesExtensions(a)} checked={agentIds.includes(a.id)} onChange={(e) => setAgentIds(toggle(agentIds, a.id, e.target.checked))} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px]">{a.name}</span>
                  <span className="block text-[11px] text-neutral-500">{takesExtensions(a) ? 'Claude Code' : `${a.cli === 'codex' ? 'Codex' : 'PowerShell'} · 적용 안 됨`}</span>
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  )
}

export { blank as blankExtension }

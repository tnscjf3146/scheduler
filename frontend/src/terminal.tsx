import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useEffect, useRef } from 'react'
import type { Agent } from './api'
import { CLI_LABEL } from './agents'

/** Shows the selected agent's terminal session. The server replays its scrollback, so switching back keeps history. */
export function TerminalPanel({ agent, onStatus }: { agent: Agent | null; onStatus: () => void }) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!agent || !host.current) return
    const term = new Terminal({
      fontFamily: "'Cascadia Mono', Consolas, 'D2Coding', monospace",
      fontSize: 13,
      cursorBlink: true,
      theme: { background: '#1f1f1f', foreground: '#d4d4d4', cursor: '#d4d4d4' },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(host.current)
    fit.fit()

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/agents/${agent.id}/terminal?cols=${term.cols}&rows=${term.rows}`)
    // The first message replays the scrollback. While xterm parses it, it answers old terminal queries
    // (e.g. "ESC[c" -> "ESC[?1;2c"); those answers must not be typed into the live shell.
    let replaying = true
    let first = true
    ws.onmessage = (e) => {
      if (!first) return term.write(e.data)
      first = false
      term.write(e.data, () => (replaying = false))
    }
    ws.onopen = onStatus
    ws.onclose = () => term.write('\r\n\x1b[90m[연결이 끊겼습니다]\x1b[0m\r\n')
    const send = (msg: object) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg))
    const input = term.onData((data) => replaying || send({ type: 'input', data }))
    const observer = new ResizeObserver(() => {
      fit.fit()
      send({ type: 'resize', cols: term.cols, rows: term.rows })
    })
    observer.observe(host.current)
    term.focus()

    return () => {
      observer.disconnect()
      input.dispose()
      ws.onclose = null
      ws.close()
      term.dispose()
    }
    // Reconnect only when a different agent is chosen, not when its status text changes.
  }, [agent?.id])

  return (
    <aside className="flex min-w-0 flex-[36] flex-col overflow-hidden rounded-xl bg-[#1f1f1f]">
      <header className="flex items-center gap-2.5 border-b border-neutral-800 bg-neutral-800/60 px-3.5 py-3">
        {agent ? (
          <>
            <span className="flex size-6 items-center justify-center rounded-full bg-neutral-600 text-[11px] font-bold text-white">{agent.name.slice(0, 1)}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-neutral-100">{agent.name}</p>
              <p className="truncate text-[11px] text-neutral-400">
                {CLI_LABEL[agent.cli]} · {agent.cwd}
              </p>
            </div>
          </>
        ) : (
          <p className="text-sm text-neutral-400">왼쪽 Agent에서 에이전트를 고르면 터미널이 열립니다</p>
        )}
      </header>
      <div ref={host} className="min-h-0 flex-1 px-2 py-2" />
    </aside>
  )
}

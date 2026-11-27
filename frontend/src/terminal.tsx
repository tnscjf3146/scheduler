import { FitAddon } from '@xterm/addon-fit'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useEffect, useRef } from 'react'
import type { Agent } from './api'
import { CLI_LABEL } from './agents'

/** The agent's terminal itself (xterm). The server replays its scrollback, so opening it again keeps history. */
export function TerminalView({ agentId, onStatus }: { agentId: string; onStatus: () => void }) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!host.current) return
    const term = new Terminal({
      fontFamily: "'Cascadia Mono', Consolas, 'D2Coding', monospace",
      fontSize: 13,
      cursorBlink: true,
      // CLIs built for dark terminals paint some text (e.g. what you type) in plain RGB white, which no palette below
      // can remap. xterm darkens any color that has too little contrast with the white background (4.5 = WCAG AA).
      minimumContrastRatio: 4.5,
      // VS Code Light+ terminal colors: the default ANSI palette (yellow, white) is unreadable on white.
      theme: {
        background: '#ffffff',
        foreground: '#333333',
        cursor: '#333333',
        selectionBackground: '#add6ff',
        black: '#000000',
        red: '#cd3131',
        green: '#107c10',
        yellow: '#949800',
        blue: '#0451a5',
        magenta: '#bc05bc',
        cyan: '#0598bc',
        white: '#555555',
        brightBlack: '#666666',
        brightRed: '#cd3131',
        brightGreen: '#14ce14',
        brightYellow: '#b5ba00',
        brightBlue: '#0451a5',
        brightMagenta: '#bc05bc',
        brightCyan: '#0598bc',
        brightWhite: '#a5a5a5',
      },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(host.current)
    fit.fit()
    // Like Windows Terminal: Ctrl+C copies when text is selected, otherwise it still interrupts.
    term.attachCustomKeyEventHandler((e) => {
      if (e.ctrlKey && !e.shiftKey && !e.altKey && e.code === 'KeyC' && term.hasSelection()) {
        if (e.type === 'keydown') {
          navigator.clipboard.writeText(term.getSelection())
          term.clearSelection()
        }
        e.preventDefault()
        return false
      }
      // Ctrl+V: leave it to the browser's own paste (xterm hears the paste event), instead of sending ^V.
      if (e.ctrlKey && !e.altKey && e.code === 'KeyV') return false
      // Shift+Enter: a new line in the prompt instead of sending it. Claude Code takes ESC+Enter as that.
      if (e.shiftKey && !e.ctrlKey && !e.altKey && e.key === 'Enter') {
        // Korean IME: the syllable being typed is committed around this key, and xterm sends it a moment later
        // (in a timeout of its own). Send the new line after that, or the syllable lands on the new line.
        const newline = () => setTimeout(() => send({ type: 'input', data: '\x1b\r' }), 30)
        if (e.type === 'keydown' && e.isComposing) term.textarea?.addEventListener('compositionend', newline, { once: true })
        else if (e.type === 'keydown') newline()
        e.preventDefault()
        return false
      }
      return true
    })

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    // The first message of every connection replays the scrollback. While xterm parses it, it answers old terminal
    // queries (e.g. "ESC[c" -> "ESC[?1;2c"); those answers must not be typed into the live shell.
    let replaying = true
    let ws: WebSocket
    let disposed = false
    let retries = 0
    // The agent keeps running on the server when the connection drops, so just connect again: the replay
    // redraws the screen as it is now.
    const connect = () => {
      ws = new WebSocket(`${proto}://${location.host}/api/agents/${agentId}/terminal?cols=${term.cols}&rows=${term.rows}`)
      let first = true
      ws.onmessage = (e) => {
        // Dark-theme CLIs (Claude Code) draw typed text in RGB white: draw that black instead.
        // ponytail: a sequence split across two messages slips through and falls back to minimumContrastRatio.
        const data = (e.data as string).replaceAll('38;2;255;255;255', '38;2;0;0;0')
        if (!first) return term.write(data)
        first = false
        replaying = true
        term.reset() // a reconnect replays everything again
        term.write(data, () => (replaying = false))
      }
      ws.onopen = () => {
        retries = 0
        onStatus()
      }
      ws.onclose = (e) => {
        if (disposed) return
        if (e.code === 4404) return term.write('\r\n\x1b[90m[에이전트가 삭제되었습니다]\x1b[0m\r\n')
        term.write('\r\n\x1b[90m[연결이 끊겼습니다. 다시 연결하는 중…]\x1b[0m\r\n')
        setTimeout(() => disposed || connect(), Math.min(1000 * 2 ** retries++, 10_000))
      }
    }
    connect()
    const send = (msg: object) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg))
    const input = term.onData((data) => replaying || send({ type: 'input', data }))
    const observer = new ResizeObserver(() => {
      fit.fit()
      send({ type: 'resize', cols: term.cols, rows: term.rows })
    })
    observer.observe(host.current)
    term.focus()

    return () => {
      disposed = true
      observer.disconnect()
      input.dispose()
      ws.close()
      term.dispose()
    }
    // Reconnect only when a different agent is chosen, not when its status text changes.
  }, [agentId])

  return <div ref={host} className="min-h-0 flex-1 px-2 py-2" />
}

/** The selected Codex or PowerShell agent's terminal (Claude Code agents get the chat, chat.tsx). */
export function TerminalPanel({ agent, onStatus }: { agent: Agent | null; onStatus: () => void }) {
  return (
    <aside className="flex min-w-0 flex-[36] flex-col overflow-hidden rounded-xl border border-neutral-200 bg-white">
      <header className="flex items-center gap-2.5 border-b border-neutral-200 bg-neutral-50 px-3.5 py-3">
        {agent ? (
          <>
            <span className="flex size-6 items-center justify-center rounded-full bg-neutral-600 text-[11px] font-bold text-white">{agent.name.slice(0, 1)}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-neutral-900">{agent.name}</p>
              <p className="truncate text-[11px] text-neutral-500">
                {CLI_LABEL[agent.cli]} · {agent.cwd}
              </p>
            </div>
          </>
        ) : (
          <p className="text-sm text-neutral-500">왼쪽 Agent에서 에이전트를 고르면 터미널이 열립니다</p>
        )}
      </header>
      {agent && <TerminalView key={agent.id} agentId={agent.id} onStatus={onStatus} />}
    </aside>
  )
}

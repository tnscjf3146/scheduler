// public/logo.svg -> ../backend/assets/scheduler.ico (exe icon). Run: pnpm icon
import { Resvg } from '@resvg/resvg-js'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'

const svg = readFileSync(new URL('../public/logo.svg', import.meta.url))
const sizes = [16, 24, 32, 48, 64, 128, 256]
const pngs = sizes.map((s) => new Resvg(svg, { fitTo: { mode: 'width', value: s } }).render().asPng())

// ICO = 6-byte header + 16-byte entry per image + the PNG files themselves.
const header = Buffer.alloc(6 + 16 * sizes.length)
header.writeUInt16LE(1, 2)
header.writeUInt16LE(sizes.length, 4)
let offset = header.length
sizes.forEach((s, i) => {
  const e = 6 + 16 * i
  header.writeUInt8(s % 256, e) // 256 is stored as 0
  header.writeUInt8(s % 256, e + 1)
  header.writeUInt16LE(1, e + 4) // planes
  header.writeUInt16LE(32, e + 6) // bits per pixel
  header.writeUInt32LE(pngs[i].length, e + 8)
  header.writeUInt32LE(offset, e + 12)
  offset += pngs[i].length
})

const out = new URL('../../backend/assets/', import.meta.url)
mkdirSync(out, { recursive: true })
writeFileSync(new URL('scheduler.ico', out), Buffer.concat([header, ...pngs]))
console.log('wrote backend/assets/scheduler.ico')

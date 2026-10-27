/**
 * Opskit exchange format: `<task-id>.opskit.zip` export and import.
 * Dependency-free: a minimal stored (no compression) ZIP writer/reader with
 * CRC32 is implemented here, so no external archiving package is needed.
 */

import { createHash } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdir, mkdtemp, readFile, rename, rm, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { stringify } from 'yaml'
import type { TaskManifest, TaskTrigger } from './contract.ts'
import { normalizeTriggerFilter } from './triggers/normalize.ts'
import {
  computeChecksums,
  parseManifest,
  rewriteManifestForImport,
  type ImportBindings,
} from './manifest.ts'
import {
  parseSeed,
  parseTriggers,
  readTaskAsset,
  serializeSeed,
  serializeTriggers,
  writeFileAtomic,
  writeTaskDir,
  type TaskAssetInput,
} from './task-writer.ts'

/* ---------------------------------------------------------------------- */
/* CRC32 (IEEE 802.3 polynomial, as required by the ZIP format)            */
/* ---------------------------------------------------------------------- */

const CRC_TABLE = new Uint32Array(256)
for (let n = 0; n < 256; n++) {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  CRC_TABLE[n] = c >>> 0
}

/** CRC32 of `data` as an unsigned 32-bit integer. */
export function crc32(data: Uint8Array): number {
  let crc = 0xffffffff
  for (let i = 0; i < data.length; i++) {
    crc = CRC_TABLE[(crc ^ data[i]) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

/* ---------------------------------------------------------------------- */
/* Stored ZIP writer / reader                                              */
/* ---------------------------------------------------------------------- */

/** Hard limits for imported archives; keep malformed uploads from exhausting memory. */
const MAX_ZIP_BYTES = 64 * 1024 * 1024
const MAX_ZIP_ENTRIES = 4096
const MAX_ZIP_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
const MAX_ZIP_NAME_BYTES = 4096

/** Reject archives that the reader/import path would reject. */
function assertZipLimits(entries: readonly ZipEntry[]): void {
  if (entries.length > MAX_ZIP_ENTRIES) {
    throw new Error(`invalid opskit: too many entries (${entries.length})`)
  }
  let totalBytes = 0
  let nameBytes = 0
  for (const entry of entries) {
    const entryNameBytes = Buffer.byteLength(entry.name, 'utf8')
    if (entryNameBytes > MAX_ZIP_NAME_BYTES) {
      throw new Error('invalid opskit: entry name too long')
    }
    nameBytes += entryNameBytes
    totalBytes += entry.data.length
    if (totalBytes > MAX_ZIP_UNCOMPRESSED_BYTES) {
      throw new Error(`invalid opskit: uncompressed data exceeds ${MAX_ZIP_UNCOMPRESSED_BYTES} bytes`)
    }
  }
  const overhead = entries.length * 76 + 2 * nameBytes + 22
  if (totalBytes + overhead > MAX_ZIP_BYTES) {
    throw new Error(`invalid opskit: archive exceeds ${MAX_ZIP_BYTES} bytes`)
  }
}

/** One file inside a zip archive. */
export interface ZipEntry {
  /** Archive path, forward slashes, UTF-8. */
  name: string
  data: Uint8Array
}

// Fixed DOS timestamp (1980-01-01 00:00:00) keeps archives deterministic.
const DOS_TIME = 0
const DOS_DATE = 0x21

/**
 * Build a ZIP archive with stored (method 0) entries only.
 * Entry order is preserved; names are flagged UTF-8.
 */
export function createZip(entries: ZipEntry[]): Buffer {
  assertZipLimits(entries)
  const body: Buffer[] = []
  const central: Buffer[] = []
  let offset = 0
  for (const entry of entries) {
    const name = Buffer.from(entry.name, 'utf8')
    const crc = crc32(entry.data)
    const size = entry.data.length

    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0) // local file header signature
    local.writeUInt16LE(20, 4) // version needed
    local.writeUInt16LE(0x0800, 6) // flags: UTF-8 names
    local.writeUInt16LE(0, 8) // method: stored
    local.writeUInt16LE(DOS_TIME, 10)
    local.writeUInt16LE(DOS_DATE, 12)
    local.writeUInt32LE(crc, 14)
    local.writeUInt32LE(size, 18) // compressed size
    local.writeUInt32LE(size, 22) // uncompressed size
    local.writeUInt16LE(name.length, 26)
    local.writeUInt16LE(0, 28) // extra length
    body.push(local, name, Buffer.from(entry.data))

    const cd = Buffer.alloc(46)
    cd.writeUInt32LE(0x02014b50, 0) // central directory signature
    cd.writeUInt16LE(20, 4) // version made by
    cd.writeUInt16LE(20, 6) // version needed
    cd.writeUInt16LE(0x0800, 8) // flags: UTF-8 names
    cd.writeUInt16LE(0, 10) // method: stored
    cd.writeUInt16LE(DOS_TIME, 12)
    cd.writeUInt16LE(DOS_DATE, 14)
    cd.writeUInt32LE(crc, 16)
    cd.writeUInt32LE(size, 20)
    cd.writeUInt32LE(size, 24)
    cd.writeUInt16LE(name.length, 28)
    // extra (30), comment (32), disk start (34), internal attrs (36),
    // external attrs (38) all stay zero
    cd.writeUInt32LE(offset, 42) // local header offset
    central.push(cd, name)

    offset += 30 + name.length + size
  }
  const cdBuf = Buffer.concat(central)
  const eocd = Buffer.alloc(22)
  eocd.writeUInt32LE(0x06054b50, 0) // end of central directory signature
  eocd.writeUInt16LE(entries.length, 8) // entries on this disk
  eocd.writeUInt16LE(entries.length, 10) // entries total
  eocd.writeUInt32LE(cdBuf.length, 12)
  eocd.writeUInt32LE(offset, 16) // central directory offset
  return Buffer.concat([...body, cdBuf, eocd])
}

/**
 * Read a ZIP archive containing only stored (method 0) entries.
 * Verifies each entry's CRC32; throws on deflated entries, truncated
 * archives, or CRC mismatches. Directory entries are skipped.
 */
export function readZip(buf: Buffer): Map<string, Buffer> {
  if (buf.length > MAX_ZIP_BYTES) throw new Error(`invalid opskit: archive exceeds ${MAX_ZIP_BYTES} bytes`)
  // Locate the end-of-central-directory record (scan the comment window).
  const floor = Math.max(0, buf.length - 22 - 0xffff)
  let eocd = -1
  for (let i = buf.length - 22; i >= floor; i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error('invalid opskit: not a zip archive (no end of central directory)')

  const count = buf.readUInt16LE(eocd + 10)
  if (count > MAX_ZIP_ENTRIES) throw new Error(`invalid opskit: too many entries (${count})`)
  let pos = buf.readUInt32LE(eocd + 16)
  const out = new Map<string, Buffer>()
  let totalBytes = 0
  for (let n = 0; n < count; n++) {
    if (pos + 46 > buf.length || buf.readUInt32LE(pos) !== 0x02014b50) {
      throw new Error('invalid opskit: corrupt central directory')
    }
    const method = buf.readUInt16LE(pos + 10)
    const crc = buf.readUInt32LE(pos + 16)
    const size = buf.readUInt32LE(pos + 20)
    const nameLen = buf.readUInt16LE(pos + 28)
    const extraLen = buf.readUInt16LE(pos + 30)
    const commentLen = buf.readUInt16LE(pos + 32)
    const localOffset = buf.readUInt32LE(pos + 42)
    if (nameLen > MAX_ZIP_NAME_BYTES) throw new Error('invalid opskit: entry name too long')
    const name = buf.subarray(pos + 46, pos + 46 + nameLen).toString('utf8')
    if (method !== 0) {
      throw new Error(`invalid opskit: unsupported compression method ${method} for ${name}`)
    }
    if (localOffset + 30 > buf.length || buf.readUInt32LE(localOffset) !== 0x04034b50) {
      throw new Error(`invalid opskit: corrupt local header for ${name}`)
    }
    const lNameLen = buf.readUInt16LE(localOffset + 26)
    const lExtraLen = buf.readUInt16LE(localOffset + 28)
    const dataStart = localOffset + 30 + lNameLen + lExtraLen
    if (dataStart + size > buf.length) {
      throw new Error(`invalid opskit: truncated data for ${name}`)
    }
    if (name.endsWith('/')) {
      if (size !== 0) throw new Error(`invalid opskit: directory entry has data: ${name}`)
    } else {
      totalBytes += size
      if (totalBytes > MAX_ZIP_UNCOMPRESSED_BYTES) {
        throw new Error(`invalid opskit: uncompressed data exceeds ${MAX_ZIP_UNCOMPRESSED_BYTES} bytes`)
      }
      const data = Buffer.from(buf.subarray(dataStart, dataStart + size))
      if (crc32(data) !== crc) throw new Error(`invalid opskit: crc mismatch for ${name}`)
      if (out.has(name)) throw new Error(`invalid opskit: duplicate entry: ${name}`)
      out.set(name, data)
    }
    pos += 46 + nameLen + extraLen + commentLen
  }
  return out
}

/* ---------------------------------------------------------------------- */
/* Export                                                                  */
/* ---------------------------------------------------------------------- */

/** All task asset files except `manifest.yml`, in stable archive order. */
function assetFiles(asset: TaskAssetInput): Map<string, string> {
  const files = new Map<string, string>()
  files.set('AGENTS.md', asset.agensMd)
  for (const key of [...asset.skills.keys()].sort()) files.set(key, asset.skills.get(key)!)
  for (const key of [...asset.scripts.keys()].sort()) files.set(key, asset.scripts.get(key)!)
  if (asset.seed !== undefined && asset.seed !== null) {
    files.set('seed/session.jsonl', serializeSeed(asset.seed))
  }
  files.set('triggers.yml', serializeTriggers(asset.triggers))
  return files
}

/**
 * Build `<task-id>.opskit.zip` in `outDir` from the task asset under `root`.
 * The manifest inside the zip carries sha256 checksums of every other file;
 * machine-local `bindings` never ship. Returns the zip path.
 */
export async function exportTask(root: string, taskId: string, outDir: string): Promise<string> {
  const asset = await readTaskAsset(root, taskId)
  const files = assetFiles(asset)
  const manifest: TaskManifest = { ...asset.manifest, checksums: computeChecksums(files) }
  delete manifest.bindings

  const entries: ZipEntry[] = [
    { name: 'manifest.yml', data: Buffer.from(stringify(manifest), 'utf8') },
    ...[...files].map(([name, content]) => ({
      name,
      data: Buffer.from(content, 'utf8'),
    })),
  ]
  const zip = createZip(entries)

  await mkdir(outDir, { recursive: true, mode: 0o700 })
  const zipPath = join(outDir, `${taskId}.opskit.zip`)
  await writeFileAtomic(zipPath, zip)
  return zipPath
}

/* ---------------------------------------------------------------------- */
/* Import                                                                  */
/* ---------------------------------------------------------------------- */

/** Options for {@link importTask}. */
export interface ImportTaskOptions {
  /** Machine-local preset bindings resolved by the caller. */
  bindings?: ImportBindings
  /** Validate the parsed trigger set before any file is written. */
  validateTriggers?: (triggers: TaskTrigger[]) => void | Promise<void>
  /** Enable the imported triggers; defaults to `false` (safe by default). */
  enabled?: boolean
}

function sha256Of(data: Buffer): string {
  return createHash('sha256').update(data).digest('hex')
}

/**
 * Import an opskit zip into `ops/<task-id>/` under `root`.
 *
 * Validates the manifest (id/format) and every declared checksum, rewrites
 * bindings via {@link rewriteManifestForImport}, forces `enabled` (default
 * `false`) onto every trigger, and stages the task under `incoming/` before
 * renaming it into place. The registry is left to the caller; returns the
 * imported task id and path.
 */
export async function importTask(
  root: string,
  zipPath: string,
  opts: ImportTaskOptions = {},
): Promise<{ taskId: string; path: string }> {
  const zipStat = await stat(zipPath)
  if (zipStat.size > MAX_ZIP_BYTES) {
    throw new Error(`invalid opskit: archive exceeds ${MAX_ZIP_BYTES} bytes`)
  }
  const zip = readZip(await readFile(zipPath))

  const manifestEntry = zip.get('manifest.yml')
  if (manifestEntry === undefined) throw new Error('invalid opskit: missing manifest.yml')
  const manifest = parseManifest(manifestEntry.toString('utf8'))

  for (const [path, expected] of Object.entries(manifest.checksums ?? {})) {
    const data = zip.get(path)
    if (data === undefined) {
      throw new Error(`invalid opskit: missing file covered by checksums: ${path}`)
    }
    if (sha256Of(data) !== expected) {
      throw new Error(`invalid opskit: checksum mismatch for ${path}`)
    }
  }

  const enabled = opts.enabled ?? false
  const triggersText = zip.get('triggers.yml')?.toString('utf8')
  const triggers: TaskTrigger[] = (triggersText === undefined ? [] : parseTriggers(triggersText)).map(
    (trigger) => normalizeTriggerFilter({ ...trigger, enabled }),
  )
  await opts.validateTriggers?.(triggers)
  const seedText = zip.get('seed/session.jsonl')?.toString('utf8')
  const seed = seedText === undefined ? undefined : parseSeed(seedText)
  const agensMd = zip.get('AGENTS.md')?.toString('utf8') ?? ''

  const skills = new Map<string, string>()
  const scripts = new Map<string, string>()
  for (const [name, data] of zip) {
    if (name.startsWith('.agents/skills/')) skills.set(name, data.toString('utf8'))
    else if (name.startsWith('scripts/')) scripts.set(name, data.toString('utf8'))
  }

  const rewritten = rewriteManifestForImport(manifest, opts.bindings ?? {})
  delete rewritten.checksums
  const taskId = manifest.id
  const finalDir = join(root, 'ops', taskId)
  if (existsSync(finalDir)) throw new Error(`task already exists: ${taskId}`)

  const incomingDir = join(root, 'incoming')
  await mkdir(incomingDir, { recursive: true, mode: 0o700 })
  const stageDir = await mkdtemp(join(incomingDir, `${taskId}-`))
  try {
    await writeTaskDir(stageDir, {
      manifest: rewritten,
      agensMd,
      skills,
      scripts,
      seed,
      triggers,
    })
    await mkdir(join(root, 'ops'), { recursive: true, mode: 0o700 })
    await rename(stageDir, finalDir)
  } catch (err) {
    await rm(stageDir, { recursive: true, force: true })
    throw err
  }
  return { taskId, path: finalDir }
}

import { mkdir, rm } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const output = path.join(root, 'dist', 'analysis-areas-1.0.0.tgz')
await rm(path.join(root, 'dist'), { recursive: true, force: true })
await mkdir(path.dirname(output), { recursive: true })
const result = spawnSync('tar', [
  '--sort=name', '--mtime=UTC 1980-01-01', '--owner=0', '--group=0', '--numeric-owner',
  '-czf', output, 'module.json', 'layer'
], { cwd: root, stdio: 'inherit' })
if (result.status !== 0) process.exit(result.status ?? 1)
console.log(output)

import { cp, lstat, mkdir, mkdtemp, readFile, readdir, rename, rm } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import os from 'node:os'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const packageMetadata = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'))
const moduleMetadata = JSON.parse(await readFile(path.join(root, 'module.json'), 'utf8'))
if (packageMetadata.version !== moduleMetadata.version) {
  throw new Error(`Package/module version mismatch: ${packageMetadata.version} != ${moduleMetadata.version}`)
}
const output = path.join(root, 'dist', `${moduleMetadata.id}-${moduleMetadata.version}.tgz`)
await rm(path.join(root, 'dist'), { recursive: true, force: true })
await mkdir(path.dirname(output), { recursive: true })
const staging = await mkdtemp(path.join(os.tmpdir(), 'analysis-areas-frontend-'))

try {
  const deploy = spawnSync('corepack', [
    'pnpm', '--filter', '@open-city-planner/analysis-areas',
    'deploy', '--prod', '--legacy', '--frozen-lockfile', staging
  ], { cwd: root, stdio: 'inherit' })
  if (deploy.status !== 0) process.exit(deploy.status ?? 1)

  // The Host module installer extracts frontend archives but deliberately does
  // not run a package manager. Flatten pnpm's lockfile-resolved production graph
  // into regular files so an installed layer outside the Host tree resolves its
  // declared runtime dependency without private Host node_modules fallbacks.
  const virtualStore = path.join(staging, 'node_modules', '.pnpm')
  const flatModules = path.join(staging, 'node_modules-flat')
  await mkdir(flatModules)
  for (const virtualEntry of await readdir(virtualStore)) {
    const packages = path.join(virtualStore, virtualEntry, 'node_modules')
    if (!(await isDirectory(packages))) continue
    for (const name of await readdir(packages)) {
      const candidate = path.join(packages, name)
      if (name.startsWith('@') && await isDirectory(candidate) && !(await lstat(candidate)).isSymbolicLink()) {
        for (const scopedName of await readdir(candidate)) {
          await copyPackage(path.join(candidate, scopedName), path.join(flatModules, name, scopedName))
        }
      } else {
        await copyPackage(candidate, path.join(flatModules, name))
      }
    }
  }
  await rm(path.join(staging, 'node_modules'), { recursive: true, force: true })
  await rename(flatModules, path.join(staging, 'node_modules'))
  await assertNoLinks(staging)

  const archive = spawnSync('tar', [
    '--sort=name', '--mtime=UTC 1980-01-01', '--owner=0', '--group=0', '--numeric-owner',
    '-czf', output, 'package.json', 'module.json', 'layer', 'node_modules'
  ], { cwd: staging, stdio: 'inherit' })
  if (archive.status !== 0) process.exit(archive.status ?? 1)
  console.log(output)
} finally {
  await rm(staging, { recursive: true, force: true })
}

async function isDirectory(target) {
  try { return (await lstat(target)).isDirectory() } catch { return false }
}

async function copyPackage(source, destination) {
  const metadata = await lstat(source)
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) return
  if (await isDirectory(destination)) return
  await mkdir(path.dirname(destination), { recursive: true })
  await cp(source, destination, { recursive: true })
}

async function assertNoLinks(directory) {
  for (const entry of await readdir(directory)) {
    const target = path.join(directory, entry)
    const metadata = await lstat(target)
    if (metadata.isSymbolicLink()) throw new Error(`Frontend archive cannot contain link: ${target}`)
    if (metadata.isDirectory()) await assertNoLinks(target)
  }
}

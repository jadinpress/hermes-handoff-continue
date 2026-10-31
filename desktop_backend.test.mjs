import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import vm from 'node:vm'

const WINDOW = '5e0e83aa-a4ed-4dd3-9975-1eff5d176106'
const OTHER_WINDOW = '6e0e83aa-a4ed-4dd3-9975-1eff5d176106'
const route = { connectionId: 'local', mode: 'local', profile: 'default', targetProfile: 'default' }
const completion = () => ({
  type: 'plugin.handoff-continue.continuation.admitted',
  connectionId: 'local', profile: 'default',
  payload: {
    desktop_window_id: WINDOW, profile: 'default', token: 'a'.repeat(32),
    stored_id: 'source', successor_id: 'successor', successor_admission_id: 'admission',
    successor_title: 'Original [Handoff 1]',
  },
})
const flush = () => new Promise(resolve => setImmediate(resolve))

test('paired and compatibility Desktop entries ship the same presentation code', async () => {
  const [paired, compatibility] = await Promise.all([
    readFile(new URL('./desktop/plugin.js', import.meta.url), 'utf8'),
    readFile(new URL('./plugin.js', import.meta.url), 'utf8'),
  ])
  assert.equal(paired.replace(/\r\n/g, '\n'), compatibility.replace(/\r\n/g, '\n'))
})

async function harness({ windowId = WINDOW, routes = [route], storage = new Map(), openSession } = {}) {
  const source = await readFile(new URL('./plugin.js', import.meta.url), 'utf8')
  const forbidden = () => { throw new Error('Desktop presentation must not touch DOM or orchestrate handoffs') }
  const context = vm.createContext({ window: new Proxy({}, { get: forbidden }), document: new Proxy({}, { get: forbidden }) })
  const opens = [], notifications = [], listeners = new Map(), disposers = []
  const host = {
    windowId,
    profileRoutes: async () => routes,
    openSession: async (...args) => { opens.push(args); await openSession?.(...args) },
    notify: value => notifications.push(value),
    request: forbidden, requestProfile: forbidden, navigate: forbidden, newChat: forbidden,
  }
  const module = new vm.SourceTextModule(source, { context })
  await module.link(specifier => {
    assert.equal(specifier, '@hermes/plugin-sdk')
    return new vm.SyntheticModule(['host'], function () { this.setExport('host', host) }, { context })
  })
  await module.evaluate()
  const ctx = {
    onEvent(type, callback) { listeners.set(type, callback); return () => listeners.delete(type) },
    onDispose(callback) { disposers.push(callback) },
    storage: { get: async key => storage.get(key), set: async (key, value) => storage.set(key, value) },
  }
  module.namespace.default.register(ctx)
  assert.equal(module.namespace.default.id, 'handoff-continue')
  return {
    opens, notifications, storage,
    async emit(event = completion()) { listeners.get(event.type)?.(event); await flush(); await flush() },
    dispose() { for (const dispose of disposers) dispose(); listeners.clear() },
  }
}

test('admitted continuation opens and selects a tab via SDK, without DOM or orchestration RPC', async () => {
  const app = await harness()
  await app.emit()
  assert.equal(app.opens.length, 1)
  assert.equal(app.opens[0][0], 'successor')
  assert.equal(app.opens[0][1].intent, 'tab')
  assert.equal(app.opens[0][1].profile, 'default')
  assert.deepEqual(app.opens[0][1].route, route)
})

test('only the originating renderer selects the successor even when two windows show the source', async () => {
  const origin = await harness(), other = await harness({ windowId: OTHER_WINDOW })
  await Promise.all([origin.emit(), other.emit()])
  assert.equal(origin.opens.length, 1)
  assert.equal(other.opens.length, 0)
})

test('duplicate completion events and plugin reload never reopen the admitted tab', async () => {
  const storage = new Map(), app = await harness({ storage })
  await Promise.all([app.emit(), app.emit()])
  assert.equal(app.opens.length, 1)
  app.dispose()
  const reloaded = await harness({ storage })
  await reloaded.emit()
  assert.equal(reloaded.opens.length, 0)
})

test('a closed or reloaded originating window is not replaced by another window', async () => {
  const original = await harness()
  original.dispose()
  const replacement = await harness({ windowId: OTHER_WINDOW })
  await Promise.all([original.emit(), replacement.emit()])
  assert.equal(original.opens.length + replacement.opens.length, 0)
})

test('profile and connection routing must match the delivering backend exactly', async () => {
  for (const mutate of [
    e => { e.profile = 'other' },
    e => { e.connectionId = 'foreign' },
    e => { delete e.connectionId },
    e => { e.payload.profile = 'other' },
    e => { e.replayed = true },
  ]) {
    const app = await harness(), event = completion()
    mutate(event)
    await app.emit(event)
    assert.equal(app.opens.length, 0)
  }
})

test('a canonical global broadcast uses its owning-profile hint, not the foreground profile', async () => {
  const owner = { ...route, profile: 'owner-alias', targetProfile: 'owner' }
  const app = await harness({ routes: [route, owner] }), event = completion()
  // The real canonical adapter leaves global publishing profile undefined.
  delete event.profile
  event.payload.profile = 'owner'
  await app.emit(event)
  assert.equal(app.opens.length, 1)
  assert.equal(app.opens[0][1].profile, 'owner-alias')
  assert.deepEqual(app.opens[0][1].route, owner)
})

test('missing, remote, or ambiguous backend routes never fall through to current focus', async () => {
  for (const routes of [[], [{ ...route, mode: 'remote' }], [route, { ...route }]]) {
    const app = await harness({ routes })
    await app.emit()
    assert.equal(app.opens.length, 0)
  }
})

test('malformed or unadmitted completion payloads cannot navigate', async () => {
  for (const field of ['desktop_window_id', 'profile', 'token', 'stored_id', 'successor_id', 'successor_admission_id']) {
    const app = await harness(), event = completion()
    event.payload[field] = ''
    await app.emit(event)
    assert.equal(app.opens.length, 0, field)
  }
  const app = await harness()
  await app.emit({ type: completion().type })
  assert.equal(app.opens.length, 0)
})

test('unloading during route discovery disarms pending presentation', async () => {
  let resolve
  const app = await harness({ routes: new Promise(done => { resolve = done }) })
  await app.emit()
  app.dispose()
  resolve([route])
  await flush(); await flush()
  assert.equal(app.opens.length, 0)
})

test('a presentation failure is reported once and never retries or submits work', async () => {
  const app = await harness({ openSession: async () => { throw new Error('private failure') } })
  await app.emit(); await app.emit()
  assert.equal(app.opens.length, 1)
  assert.equal(app.notifications.length, 1)
  assert.equal(JSON.stringify(app.notifications).includes('private failure'), false)
})

test('unloading during SDK activation invalidates the final selection fence', async () => {
  let resolve, selected = false
  const activated = new Promise(done => { resolve = done })
  const app = await harness({ openSession: async (_id, options) => {
    await activated
    if (options.isCurrent?.() !== false) selected = true
  } })
  await app.emit()
  assert.equal(app.opens.length, 1)
  app.dispose()
  resolve()
  await flush(); await flush()
  assert.equal(selected, false)
})

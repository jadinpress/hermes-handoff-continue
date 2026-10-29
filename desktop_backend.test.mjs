import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import vm from 'node:vm'

test('Desktop compatibility entry never touches DOM, focus, SDK, or RPC', async () => {
  const source = await readFile(new URL('./plugin.js', import.meta.url), 'utf8')
  const forbidden = () => { throw new Error('Desktop must not orchestrate handoffs') }
  const context = vm.createContext({ window: new Proxy({}, { get: forbidden }), document: new Proxy({}, { get: forbidden }) })
  const module = new vm.SourceTextModule(source, { context })
  await module.link(forbidden)
  await module.evaluate()
  const ctx = new Proxy({}, { get: forbidden })
  module.namespace.default.register(ctx)
  assert.equal(module.namespace.default.id, 'handoff-continue')
  assert.match(module.namespace.default.description, /backend/i)
})

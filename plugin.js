import { host } from '@hermes/plugin-sdk'

// Presentation only. Creation, artifact checks and prompt admission stay backend-owned.
export default {
  id: 'handoff-continue',
  name: 'Handoff and Continue',
  description: 'Backend-owned handoff continuation. Use /handoff-continue [status|cancel].',
  register(ctx) {
    // Older desktops continue on the backend without guessing a destination window.
    if (typeof host.windowId !== 'string' || !host.windowId) return
    let alive = true
    const seen = new Set()
    ctx.onDispose(() => { alive = false })
    ctx.onEvent('plugin.handoff-continue.continuation.admitted', event => {
      const payload = event.payload
      const id = value => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,160}$/.test(value)
      if (!alive || event.replayed || !payload || payload.desktop_window_id !== host.windowId
          || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(payload.profile || '')
          || !/^[0-9a-f]{32}$/.test(payload.token || '')
          || !id(payload.stored_id) || !id(payload.successor_id)
          || !id(payload.successor_admission_id)) return
      const connectionId = event.connectionId
      if (typeof connectionId !== 'string' || !connectionId) return
      const key = `tab:${host.windowId}:${connectionId}:${payload.profile}:${payload.token}`
      // Reserve synchronously: duplicated notifications can arrive while route discovery awaits.
      if (seen.has(key)) return
      seen.add(key)
      void (async () => {
        const routes = await host.profileRoutes()
        // A multiplex global event proves its receiving connection, not a profile.
        // payload.profile selects a known local owner route; it is not authorization.
        const matches = routes.filter(route => route.mode === 'local'
          && route.connectionId === connectionId && route.targetProfile === payload.profile
          && (!event.profile || event.profile === route.profile))
        if (!alive || matches.length !== 1 || await ctx.storage.get(key)) return
        // Consume before opening: uncertain presentation must not steal focus again on reload.
        await ctx.storage.set(key, true)
        if (!alive) return
        await host.openSession(payload.successor_id, {
          intent: 'tab', profile: matches[0].profile, route: matches[0], isCurrent: () => alive,
        })
      })().catch(() => {
        if (alive) host.notify({ kind: 'error', message: 'Handoff continued, but its tab could not be opened. Open the successor from the session list.' })
      })
    })
  },
}

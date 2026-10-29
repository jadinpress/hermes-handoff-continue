// Compatibility marker for existing paired Desktop installations.
// All commands and orchestration live in the native Python backend. In
// particular, never subscribe to the old renderer claim/completion events.
export default {
  id: 'handoff-continue',
  name: 'Handoff and Continue',
  description: 'Backend-owned handoff continuation. Use /handoff-continue [status|cancel].',
  register() {},
}

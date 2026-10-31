# Originating-window successor tab implementation plan

> **For agentic workers:** Use behavior-first TDD and scoped verification. Never modify or restart the running Hermes source checkout.

**Goal:** After a handoff continuation is admitted, open and select its successor as a tab only in the renderer that invoked the command.

**Approved design:** Capture a renderer-lifetime UUID at command dispatch; propagate it as optional `desktop_window_id` through the gateway's existing native command context; retain it in durable job metadata. Publish a namespaced plugin event only after the successor admission is persisted. The Desktop half compares the exact UUID, validates the receiving connection/profile, deduplicates the request token, and calls `host.openSession` with `intent: 'tab'`. A closed or reloaded renderer is never replaced by another window. No DOM, computer-use, lifecycle changes, prompt replay, or new model permissions.

**Architecture:** The backend remains the sole workflow owner. Presentation failure never changes the admitted handoff result. The SDK exposes only a renderer identity, not a new tab subsystem. The existing public `broadcast_plugin_event` is used for the current in-process plugin configuration; host-isolated callback delivery is not assumed and must be documented separately.

**Tech stack:** Python canonical RPC contracts/native plugins; TypeScript React Desktop SDK; dependency-free ESM plugin; unittest and Vitest.

## Constraints

- Core changes belong in `C:/Users/jadin/workspace/hermes-handoff-window-core` on `feat/handoff-origin-window`, not the live runtime checkout.
- Plugin changes belong in this repository on `feat/origin-window-tab`; do not push or publish.
- Validate supplied window IDs as canonical UUID strings without trimming or coercion; omission preserves backend-only behavior.
- Preserve existing session/profile authorization, admission/cancellation boundaries, source title inheritance, and no-replay guarantees.
- No automatic selection when identity, route, or profile is absent/ambiguous. No routing through current focus.
- The current installed isolation mode is `in_process`; isolated plugin-host events are not a verified supported route.
- No restart, forced reload of live Python modules, real user continuation, or source-checkout history changes.

## Task 1: Window identity and command context

Files: Desktop `src/lib/desktop-window-id.ts`, `src/sdk/index.ts`, `src/app/session/hooks/use-prompt-actions/slash.ts`; canonical `gateway/session_commands.py`, `gateway/run_inbound_hooks.py`; `tui_gateway/contracts/tools_commands.py` and canonical declarations as required; generated gateway contracts; focused existing command/source tests.

- [ ] Add behavioral tests to existing real Desktop hook/SDK tests: extension invocation carries a stable UUID; SDK returns the same UUID; a second renderer module instance has a different identity; no storage/focus dependency. Run and observe assertion failure before implementation.
- [ ] Add backend tests proving optional exact window-ID propagation through both slash.exec and command.dispatch, malformed IDs reject before callbacks, omitted IDs and legacy handler signatures remain compatible. Run focused tests through `scripts/run_tests.sh` and observe the intended failure.
- [ ] Implement the smallest identity helper, SDK property and context propagation. Preserve the captured UUID on fallback. Regenerate shared TypeScript/OpenRPC contracts with `scripts/gen_gateway_contracts.py`.
- [ ] Run the focused tests plus contract-generation checks, type checking and changed-file lint checks.

## Task 2: Backend admission notification

Files: plugin `__init__.py`, `backend.py`, `test_backend.py`, `test_protocol.py`, `test_workflow.py`.

- [ ] Add a command test with a valid UUID and assert exact service context; malformed IDs must not start work. Observe RED before changing capture logic.
- [ ] Add a workflow test that injects a notification recorder and checks persisted `phase == complete` and a successor admission before notification. Observe RED before implementation.
- [ ] Add optional window ID to the service start state. After the final successful state save, invoke a best-effort namespaced publisher with only window/profile/request/source/successor/admission/title metadata. Never notify on cancellation, uncertain send or failed artifact verification.
- [ ] Test notification failure leaves the backend complete and does not resend; absent window ID does not publish. Preserve state and handles exactly.

## Task 3: Desktop presentation

Files: plugin `plugin.js`, paired `desktop/plugin.js`, `desktop_backend.test.mjs`, `README.md`.

- [ ] Replace the inert-marker test with a VM SDK-boundary harness using throwing DOM proxies. Add a valid completion test and observe no tab opened against the existing marker.
- [ ] Implement a lifetime-scoped event listener, strict payload/window validation, exact local connection/profile route selection, duplicate suppression before awaits, and `host.openSession(successor_id, { intent: 'tab', profile, route })`.
- [ ] Test two renderer IDs receiving the same event, later focus changes, duplicate concurrent events, disposed listeners, profile/connection mismatch, ambiguous/missing routes, malformed events, and rejected presentation without backend calls.
- [ ] Document automatic selected-tab behavior, older Desktop/backend-only fallback, renderer closure/reload semantics, and the in-process event-delivery prerequisite.

## Task 4: Integration and rollout gates

- [ ] Run all plugin tests, syntax checks, core targeted tests, regenerated-contract consistency, changed-file lint/type checks and a Desktop production build in the isolated clone.
- [ ] Independently review the frozen diffs for identity/route races, replay, cancellation and unrelated changes; correct defects and rerun relevant tests.
- [ ] Commit only verified source/test/documentation changes in each repository. Do not include dependencies, build outputs or private runtime evidence.
- [ ] Compare installed plugin bytes/provenance before any supported deployment. Report code/tests/build and live activation separately. If activation requires restarting the shared owner or Desktop, stop at that approval boundary rather than bypassing it.
- [ ] A real disposable end-to-end model handoff requires a separately scoped smoke-test authorization; mocked protocol tests are not live UI/model evidence.

## Verified checkpoint (supersedes the authoring checklist above)

- Tasks 1–3: implementation and scoped automated verification complete. The stable
  module-lifetime ID and additional rejection cases include already-GREEN regression
  coverage; they do not establish separate historical RED checkpoints.
- Review found and corrected three real integration gaps: canonical global-event
  provenance across profile switches, owner-route retention on ordinary session
  tiles/keep-sets, and plugin disposal while SDK activation is pending. The fixes
  have behavior-first adapter/boot and actual SDK-to-core regression tests.
- Global multiplex events authenticate the receiving transport only; their profile
  stays undefined. The plugin resolves a profile hint against a unique known local
  route on that exact connection, never current chrome. SDK currentness is checked
  after activation and immediately before selection.
- Latest combined verification: 468 Desktop tests; 64 Python gateway/contract/event
  tests (one Linux-only skip); 46 Python plugin tests; 12 presentation tests.
  TypeScript, changed-file lint, generated contracts and the production build pass.
- Source commits preserve the checked candidate. No push, installed-tree replacement,
  runtime switch, Desktop restart, gateway restart, or real-model smoke is approved
  by these source checks. Preserve both feature branches for coordinated activation.
- Live activation and actual tab/model evidence remain pending separate approval.

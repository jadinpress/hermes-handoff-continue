# Handoff and Continue

Version 2 runs entirely in the native Python backend. Desktop does not orchestrate,
read files, claim events, open sessions, or change focus. The tiny `plugin.js` is
an inert compatibility marker for existing paired installations, not a controller.

## Use

- `/handoff-continue` prepares a verified durable handoff and admits a continuation
  into one fresh, visible session owned by the same profile.
- `/handoff-continue status` reports progress, the durable file, successor ID when
  known, and a safe error diagnosis. It sends no model prompt.
- `/handoff-continue cancel` disarms subsequent orchestration. Cancellation is checked
  after the last state save immediately before each create/submit RPC. Already-submitted
  or in-flight RPCs cannot be revoked; known successor handles are preserved.

Let the source turn finish first. You can switch chats or work elsewhere immediately;
there is no focus lease. Open the successor manually from the normal session list
(`Original title [Handoff 1]`, then `[Handoff 2]`, and so on). Only a trailing
`[Handoff N]` suffix is incremented; other title text is preserved. Untitled sources
use `Untitled session [Handoff 1]`. The chosen successor title is saved in the job;
request tokens remain in durable metadata rather than the visible title.
If needed, the base title is shortened to fit the gateway's title-length limit,
always retaining the complete numbered suffix.
Creation never selects by title: the backend renames its fresh successor by exact
ID and verifies the result. A conflicting title or uncertain rename stops before
continuation, preserves the successor handle, and is never automatically retried.
There are no palette actions or automatic navigation.
No separate `handoff` skill is needed: the plugin embeds both the handoff-writing
instructions and the successor's resume instructions. It does not install or modify
any skills. Task-specific skills may be used when already available and relevant;
an essential missing task capability is reported as a blocker rather than installed
automatically.

## Backend flow and safety

1. Capture the gateway's explicit `source`, `platform`, and canonical chat identity.
   Default-profile `source.profile=None` is resolved against the registered home.
   Legacy bound Desktop context remains supported; messaging/unknown contexts and
   mismatched profiles fail closed. No renderer claim/broadcast is involved.
2. Acquire an OS file lock per source, persist the request, and attach a daemon worker
   to the already-running local gateway through its authenticated canonical client.
   Discovery never starts/restarts a gateway or falls back to a remote URL. Validate
   the absolute owner profile home and required protocol capabilities.
3. Attach to the source before submitting; require idle/no pending work and capture
   cwd, model/provider, reasoning and service tier. Pause active source goal, loop,
   and heartbeat automation (never clear it) to prevent the old chat continuing in
   parallel. Paused automation is listed in status and is not automatically resumed.
4. Ask the source agent to use backend file tools and the embedded handoff instructions.
   The document covers the original goal and next action, authoritative references,
   working state, verification and blockers, approvals and stopping boundaries, and
   optional suggested skills. It must redact secrets and unnecessary personal information.
   Require a successful canonical completion correlated to both session and admission ID,
   including the exact per-request ready line. Read only the expected local artifact:
   bounded UTF-8, no NUL bytes, complete receipt, regular file under the durable root.
5. Create a fresh empty-transcript session using canonical `request_id`, `source=gui`,
   and captured settings (`reasoning`, not legacy `reasoning_effort`). Submit a prompt
   instructing it to read the verified file, continue the original goal, and preserve
   all approval boundaries. No new consequential-action permissions are granted.
6. Persist both admission IDs and the successor handle; detach subscriptions on exit.
   A successful transfer means the continuation was admitted, **not** that its work
   finished. Transport loss, ambiguous replies, cancellation, unload/reload, or stale
   worker state never trigger an automatic resend.

An existing request blocks another start for that source, including an uncertain
request. Inspect status and the known sessions rather than deleting state and retrying.
Different sources use separate locks and can run concurrently. Workers stop after a
bounded wait; a backend process exit leaves a stale request marked interrupted on
the next read. No separate daemon, public endpoint, Desktop DOM or computer-use is needed.

## Storage and deployment

Each profile uses its own resolved `$HERMES_HOME`:

- `handoffs/<request token>.md` — durable handoff, outside prunable scratch.
- `plugin-data/handoff-continue/jobs/<sha256 source ID>.json` — atomic job metadata.
- Adjacent `.lock` and request-qualified `.cancel` files — concurrency/cancellation.

Old handoff files and sessions remain untouched. Pre-v2 renderer state is not replayed.
Install `__init__.py`, `backend.py`, and `plugin.yaml` into the owning profile's
`plugins/handoff-continue/`. The default package retains the inert `desktop/plugin.js`;
named profiles need no renderer. Preserve the existing enable list and Desktop choice.
Hermes and its Python environment provide `filelock` and the canonical gateway client.
Run plugin doctor before activation. A live native reload re-registers other plugins;
obtain approval before using it during parallel work. No application restart is required.

Each additional profile needs explicit provisioning/enablement; no global watcher is added.
Rollback restores backed-up package files and the compatibility renderer, then reloads
the approved profile scopes. It does not delete handoffs, sessions, or job records.

## Verification

Run `npm test`, `npm run check`, `hermes plugins doctor . --ci`, and `git diff --check`.
Python tests cover explicit command identity, the real canonical event/receipt shapes,
source/admission correlation, file verification, source automation pause, OS locks,
cancellation, unload, stale/corrupt state, and uncertain sends. The Node VM test rejects
any Desktop SDK import or DOM access. These automated tests use fake gateway I/O;
live slash dispatch and a synthetic real-model handoff are separate verification gates.

### Compatibility and verification limits

Handoff preparation and resumption are self-contained; no separate skill download
or installation is required. This plugin still depends on Hermes internal Python APIs
and a running local canonical gateway advertising `durable-admission-v1`, `event-replay-v1`, and
`local-cli-create-v1`. It also requires revision-checked session renaming and the
session-control APIs used above. Compatibility with arbitrary Hermes versions,
remote gateways, and messaging platforms is not established. The gateway and
Hermes Python modules must be available in the environment used for testing.

The automated suite uses synthetic sessions and temporary directories; it does not
send model prompts or prove end-to-end completion by a real successor agent.
The plugin reports transfer/admission, not completed successor work.

The self-contained prompts also passed a separate real-model smoke test: a source
wrote a verified handoff and a fresh successor read it, completed a fictional file
task, and finished successfully without invoking a handoff skill. See
`VERIFICATION.md` for the evidence scope, checks, and remaining limitations.

## Privacy

The source package does not include runtime handoffs, conversation histories,
credentials, memory databases, or profile configuration. At runtime, handoff files
can contain private task context and job metadata can contain local paths, session
identifiers, model settings, and session titles. Keep those artifacts private and
review them before sharing diagnostics. A handoff is submitted to the configured
model provider through Hermes; this plugin does not make that interaction offline.

The Git ignore rules help prevent accidental additions but cannot protect files
that are force-added or already tracked. See `SECURITY.md` for sharing guidance.

## License

MIT. See `LICENSE`. This is an independent community plugin, not an official
Hermes or Nous Research release.
# Verification scope

## Real-model smoke test

The self-contained prompts in source revision `b9ed1a9` passed a real-model test
using the candidate's actual command handler and backend against an already-running
local Hermes canonical gateway. The test used `gpt-6.1-sol` through `openai-codex`
with medium reasoning. It did not install the candidate or replace the live plugin.

The test used a disposable source session, a fresh successor, fictional context,
and a narrowly scoped local file-writing task. Observed results:

- The source acknowledged the initial setup without performing the deferred task.
- The source wrote and read back a durable handoff using the embedded instructions.
- The handoff preserved the original goal, expected output, explicit non-approval,
  and all requested document sections.
- The backend verified the handoff and admitted continuation into a fresh successor.
- The successor title matched the backend's recorded title, and its transcript
  contained one user continuation prompt, not a copied source conversation.
- The successor read the exact handoff, wrote the exact expected UTF-8 result bytes,
  read the result back, and finished successfully.
- Both the source handoff and successor had terminal, completed, nonfailed receipts.
- The source and successor used only scoped `read_file` and `write_file` tools.
  Neither invoked a handoff skill or read a skill file. The explicitly forbidden
  file was not created.
- Repeating the candidate start command was refused rather than replayed.

The initial evidence checker incorrectly expected read-file contents in the display
transcript. That projection omits those contents. Verification was corrected by
correlating the exact read path and tool-call ID with the committed turn result;
the model work was not replayed. This was a checker issue, not a plugin code change.

Raw transcripts, local paths, session/admission identifiers, handoff content, and
private runtime state are intentionally excluded from this repository.

## Fresh installation and native slash smoke test

Source revision `383e993` was installed through `hermes plugins install` into a new,
disposable profile created with `--no-skills --no-alias`, without cloning another
profile's configuration or credentials. The profile had no handoff skill. The
installer was given a local Git source and the exact 40-character revision with
`--ref`, plus `--yes-deps --enable`; no repository was published for this test.

Observed results:

- The installer resolved the repository name to the manifest ID `handoff-continue`.
- Plugin show reported enabled; plugin doctor passed. The running gateway reported
  one loaded command and no plugin load error for the disposable profile.
- The native command appeared in the command catalog and slash completions.
- Actual gateway `slash.exec` dispatch returned the expected fresh-session status,
  usage rejection for invalid arguments, and no-active-handoff idle cancellation.
- These checks did not create handoff jobs or running/pending model work. No model
  call or credential copy was needed for the installation smoke test.
- The installed checkout was at the pinned commit with a clean tracked tree.
  Checkout line-ending conversion changed raw file hashes; normalized source
  matched, and all 37 Python tests plus the Desktop isolation and JavaScript syntax
  checks passed against the installed files themselves.

On this Windows Git setup, the initial triple-slash local file URI did not clone;
the validated drive-qualified `file://` form succeeded. This is a local test
transport detail, not evidence of failure of the prospective GitHub HTTPS install.
The installer offered optional Node setup due to the developer `package.json`;
skipping it did not prevent enablement or command dispatch.

The CLI reported Hermes Agent `v0.22.5 (2026.9.24)`, stable, local revision
`bf0203a794a0`. Python 3.14.9 and Node 24.13.0 were used for developer checks.
This records the observed environment, not a minimum-version compatibility claim.

## Automated checks

The candidate also passed 37 Python tests, the Desktop no-access test, JavaScript
syntax checking, plugin doctor, and whitespace checks. New prompt regressions were
observed failing before their implementation, then passing. Source and Git history
were scanned for secrets; targeted personal-information checks were also run.
These checks reduce risk but cannot guarantee absence of every sensitive detail.

## Limits

- The real-model test exercised the candidate command handler and backend, not
  installed slash-command dispatch. Fresh-install discovery and non-model slash
  dispatch were verified separately; a full model transfer from the fresh profile
  was not performed because that profile was deliberately left without credentials.
- A handoff skill existed in the real-model test's profile but was not invoked.
  The separate fresh-install profile had no handoff skill, but was not a separate
  operating-system or clean-machine installation.
- This is one provider/model and one local gateway environment, not a general
  compatibility matrix. No remote gateway or messaging-platform support is claimed.
- No service restart, UI navigation, publication, or production plugin replacement
  was needed. The plugin's status still reports continuation admission, not the
  eventual completion of arbitrary successor work.

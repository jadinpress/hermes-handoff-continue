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
runtime metadata are intentionally excluded from this repository.

## Automated checks

The candidate also passed 37 Python tests, the Desktop no-access test, JavaScript
syntax checking, plugin doctor, and whitespace checks. New prompt regressions were
observed failing before their implementation, then passing. Source and Git history
were scanned for secrets; targeted personal-information checks were also run.
These checks reduce risk but cannot guarantee absence of every sensitive detail.

## Limits

- The real-model test exercised the candidate command handler and backend, not
  installed slash-command discovery or a reloaded production plugin.
- A handoff skill existed in the host environment but was not invoked. The test
  did not provision a separate machine with that skill physically absent.
- This is one provider/model and one local gateway environment, not a general
  compatibility matrix. No remote gateway or messaging-platform support is claimed.
- No service restart, UI navigation, publication, or production plugin replacement
  was needed. The plugin's status still reports continuation admission, not the
  eventual completion of arbitrary successor work.

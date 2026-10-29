# Security and privacy

## Runtime data is private

Handoff documents may contain sensitive task context. Job metadata can contain
session identifiers, local paths, model/provider settings, and session titles.
Do not commit or upload `handoffs/`, `plugin-data/`, conversation transcripts,
profile configuration, credentials, memory databases, or diagnostic logs.
The ignore rules are preventive guidance, not an access-control boundary.

The plugin uses the authenticated local Hermes gateway and the configured model
provider. Local gateway attachment does not mean handoff content stays offline.
Starting a handoff can incur model-provider usage charges. A continuation retains
the existing approval boundaries; it does not grant additional permissions.

## Reporting a problem

Never include real secrets, personal information, private handoff content, or
unredacted runtime state in a public issue. Use synthetic data and the smallest
reproduction possible. A dedicated private reporting channel has not yet been
established; do not assume a public issue is a confidential disclosure channel.

## Before sharing a fork or release

- Review every included file and all reachable Git history and tags.
- Scan both the source tree and Git history with a secret scanner.
- Inspect author/committer names, emails, paths, hostnames, and profile names.
- Export only explicitly reviewed source files; do not archive a Hermes home.
- Confirm that generated files, runtime data, and credentials are not tracked.
- Rescan the final commit before pushing. No automated scan guarantees absence
  of all sensitive data, and deleting a public leak cannot recall existing copies.

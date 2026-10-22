# Stage59 — Live, read-only integration ancestry gate

This research task does **not** merge any PR and does **not** establish that
NeXium is a production-quality macOS Switch emulator. Its goal is to make
hidden parent/branch drift observable before reviewing the experimental stack.

## Inputs and rules

The `nexium-intel-stack-audit.yml` workflow runs on the dedicated Stage59
Draft PR, with a GitHub token scoped to **read-only contents and pull requests**.
The auditor fetches the current open PRs and `main` head, then follows the
real head/base branch links all the way from Stage59 PR #61 to bootstrap PR #1.
Every PR in that connected chain must remain open and Draft.

GitHub's pull-request `base.sha` can reflect a historical comparison snapshot,\nnot the live base branch tip. Before comparison, the collector therefore\nresolves each child's base ref to its **current parent PR head SHA** (or\nthe current `main` SHA), retaining the reported older SHA separately. This\nis essential to detect the three known diverged branches rather than hiding\nthem behind old PR metadata.\n\nFor each connected PR, the auditor requests GitHub's exact SHA-to-SHA compare
instead of using possibly ambiguous branch names with `/`. It requires:
- The Stage59 head SHA from the triggering PR event matches the live PR.
- Ancestry is unique, cycle-free, rooted in PR #1 and reaches the inspected
  `main` SHA; all adjacent base SHA fields match the parent's head SHA.
- Every ancestry edge has a corresponding comparison of those exact SHAs.
- Differences between current bases and original child heads are **listed**
  as divergence rather than silently treated as integrated.
- All API errors and incomplete, inconsistent or out-of-bounds evidence block
  the audit. No token, raw API dump, guest data or private log is uploaded.

The command reports `STAGE59_STACK_AUDIT_REVIEW_REQUIRED` on a structurally
complete audit. Its JSON **always** contains
`"main_merge_approved": false` and `"integration_requires_review": true`,
even when all edges happen to be fast-forwardable. The CI result means only
that the graph has been inspected and classified.

## Current research context (22 October 2026)

The verified Stage58 head is `65d74086858e39f56c735ea4e85e68ee5a4cfd50`
and CI #191 finished successfully: **405 Python tests**, native x86_64
`rustarmic` build, real guest public homebrew NRO, and Stage54–57 proof
checks. Its sanitized manifest artifact is #12391281449.

Before Stage59, the direct chain from Stage58 to `main` consisted of **27
Draft PRs**. Three historical ancestry comparisons are diverged:

| PR | Old stage | Missing ancestor commits |
| --- | --- | ---: |
| #16 | Stage29 relative to Stage28 | 1 |
| #39 | Stage39 relative to Stage38 | 2 |
| #41 | Stage40–41 relative to Stage39 | 1 |

Stage58 restored the missing source-level diagnostic fixes in a *new top
commit*; it intentionally did **not** rewrite historical PR heads or pretend
that their old ancestry was now linear. This is why an integration audit is
necessary even after fully successful native CI.

## Remaining release gates

Integrate only after separately reviewing historical ancestor edits, deciding
how to preserve source fixes from diverged branches, and running the complete
workflow on the actual proposed integrated result. The study has not yet
established commercial game compatibility, rendering, production GUI, audio,
physical controller support or Nintendo Switch hardware behavior.

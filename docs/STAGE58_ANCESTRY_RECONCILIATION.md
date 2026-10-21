# Stage58 — reconciliation of stale ancestor diagnostics

This document records a **source-level integration reconciliation**, not a rebase
or merge of earlier PR branches. Earlier verified branch heads and CI remain
unchanged. It does not establish production readiness or physical controller,
commercial game, or Nintendo Switch execution.

## Why this is necessary

On 2026-10-22, the 26 open Draft PRs along the direct path from PR #59 to
`main` were compared **head against its actual current base branch**. Three
edges were diverged even though the PR refs remained connected and GitHub
reported they could be merged:

| Earlier PR | Parent commits absent from its head | Impact |
| --- | ---: | --- |
| #16 Stage29, based on Stage28 | 1 | Stage28's audio-disabled constructor phase audit incorrectly required checkpoint 01 |
| #39 Stage39, based on Stage38 | 2 | Stage38 no-NRO/no-NPad-tick negative control was missing its explicit classification and unit test |
| #41 Stage40–41, based on Stage39 | 1 | Stage39's guarded zero-handle source-anchor classification was absent |

The missing parent commit SHAs:
- `1f70d6bb37e9b6b2a78d158d5b818fb4f4e853c6` (Stage28)
- `f601651c7a1569524a4612f38940e1d3cbeed4bc` (Stage38)
- `586d334cf8668f7fdccbb53c69ca859dc4dc6ab8` (Stage38)
- `f9b6cbad78d4e71049252cad9245a940dcd7b50c` (Stage39)

## What Stage58 restores

1. Stage28 workflow accounts for the intentional omission of UI audio checkpoint
   01 when audio is disabled, but still requires the remaining phases in exact
   order and rejects unexpectedly executed audio initializers.
2. Stage38 distinguishes three different conditions: a positive source-bound
   B round trip; no NPad tick observed without any NRO; or some NPad samples
   without a confirmed round trip. Only the explicit no-tick/no-NRO condition
   is allowed as a negative control; it is never counted as a successful HID
   input round trip.
3. Stage39 recognizes an absent zero-handle guard as a specific fail-closed
   handle-validation contract mismatch, rather than an unrelated missing-string
   parser error.

Every change is based on the corresponding historical parent commit, with
additional targeted Stage38 regression coverage. Stage54–57 provenance,
manifest replay, NRO, and Mach-O structural gates remain enabled on the
new Stage58 branch and must be verified on its exact revision.

## Integration constraints

- Do **not** move or rewrite Stage28, Stage38, Stage39, Stage40–41, or any
  verified Stage54–57 historical branch simply to make its ancestry appear
  clean. Stage58 is a separate stacked reconciliation PR.
- These source patches **do not make the old branch comparisons show zero
  behind commits**; a final integration must still account for the actual
  merge semantics of all ancestor PRs and rerun the consolidated test suite
  after merge.
- The latest Stage57 CI #190 has already passed on its original revision with
  403/403 tests and five checked file segments, 32 sections, and five original
  NPad samples. Stage58 requires independent CI evidence.
- No ROM, firmware, keys, private guest memory, raw logs, or screenshots are
  added or uploaded.

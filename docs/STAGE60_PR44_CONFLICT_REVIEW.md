# Stage60 — first blocking virtual merge conflict (PR #44)

**Source:** GitHub Actions [local merge rehearsal #4](https://github.com/stanmasked/nexium-macos-intel/actions/runs/39732329939), on commit `66154d39b7bd14701159d440bee9832876c4a8aa`.

This is a diagnosis and suggested manual integration resolution, **not an applied merge or production certification**. The workflow is intentionally red when the virtual Git merge cannot proceed without explicitly choosing a resolution.

## Reproduced, scoped outcome

- 29 ancestor Draft PRs requested; **15 complete**, the first conflict occurred while applying **PR #44 (Stage42)** as the 16th entry.
- Git returned the single conflicted path:
  `scripts/audit_guest_hid_mapping_path.py`.
- All **13/13** offline Stage60 merge/rejection tests passed in the same run.
- No checkout `HEAD`, `main`, GitHub PR branch, or remote ref was altered.

## Why this file conflicts

PR #41 (Stage40–41) inherits the old Stage39 form: it unconditionally extracts the `if handle == 0 {` source block and then computes `has_zero_handle_warning`. The *updated* Stage39 PR #39 had independently added a guarded extraction that checks for the source anchor before parsing; this historical change is **not contained in PR #41**.

PR #44 Stage42 independently added a different pre-check:
`if 'if handle == 0 {' not in map_svc: raise ValueError(...)`.

When the rehearsal first virtually merges the corrected Stage39 history and the Stage40–41 branch, and then Stage42, Git sees overlapping edits to exactly these lines. It correctly refuses to guess which implementation to keep.

## Proposed manual conflict resolution

For an eventual integration branch, review and retain the **Stage58 reconciled logic** from
`work/intel-stage58-reconcile-ancestor-audits`:

- Initialize `has_zero_handle_warning = False`.
- Extract `zero_handle_branch` only if `'if handle == 0 {' in map_svc`.
- Raise `ValueError("expected current size-based mapping/handle-validation behavior changed")` via the existing final contract check if the guard is absent.
- Keep the independent HID mapping, no-op unmap limitation, and source-contract assertions; do not treat a missing anchor as successful mapping.
- Confirm `tests/test_guest_hid_mapping_path.py` still rejects a source with the zero-handle condition removed.

The reconciled file's SHA at Stage60 head is Git **blob** `3bae901b585bde27a2d55c82faf4366b5c99d74d`. This is a **candidate for human-reviewed resolution**, not an automatic `ours` or `theirs` policy.

## Next verification

1. Keep the full Stage60 replay as a red, fail-closed merge gate until an **explicit** integration resolution is reviewed.
2. Rehearse the chosen resolution on **temporary local Git objects only** to discover whether any *later* PRs conflict; do not rewrite historical branch heads.
3. Preserve all source-based regression tests and rerun complete Python, native Intel and guest diagnostics on the actual combined tree.
4. Never merge a 29-PR experimental port directly to `main` just because isolated CI jobs are green. No real Nintendo Switch/game support is certified.

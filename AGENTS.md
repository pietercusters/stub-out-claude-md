# Agent instructions for stub-out-claude-md

This repo contains a single [pre-commit](https://pre-commit.com) hook that
keeps `AGENTS.md` as the source of truth for agent instructions and
`CLAUDE.md` as an `@AGENTS.md` import stub, per directory. See README.md for
the full behavior table.

## Layout

- `src/stub_out_claude_md.py` — the entire hook: symlink normalization, then
  a per-directory decision table. Stdlib only; keep it that way.
- `.pre-commit-hooks.yaml` — hook metadata consumed by pre-commit.
  `types_or: [file, symlink]` is load-bearing: without it, symlinked files
  never reach the hook.
- `tests/test_stub_out_claude_md.py` — one test per decision-table row, plus
  idempotence, symlink, non-UTF-8, and git-index (mode 120000) cases.

## Commands

- `uv sync` — set up the environment (project is uv-managed).
- `uv run pytest` — run the unit tests.
- `uv run pre-commit run --all-files` — run this repo's own hooks.
- End-to-end: `uv run pre-commit try-repo . stub-out-claude-md --verbose --all-files`
  from a scratch consumer repo (only *tracked* files reach the shadow repo —
  `git add` first).

## Conventions

- Never let the hook discard user content: fixes must move, merge, or
  deduplicate bytes, or fail with an instruction. New decision-table rows
  need a matching test, and every auto-fix must be idempotent (second run
  exits 0).
- All content operations are byte-level so non-UTF-8 files survive verbatim.
- Releases are git tags (`vX.Y.Z`); consumers pin `rev:` to a tag and update
  via `pre-commit autoupdate`. Bump `version` in `pyproject.toml` when tagging.
  Release with `gh release create vX.Y.Z --generate-notes`; the Release
  workflow (`.github/workflows/release.yml`) then verifies the tag matches
  the pyproject version and re-runs the tests at the tagged commit.

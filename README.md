<div align="center">

# Stub out CLAUDE.md

[![CI](https://github.com/pietercusters/stub-out-claude-md/actions/workflows/ci.yml/badge.svg)](https://github.com/pietercusters/stub-out-claude-md/actions/workflows/ci.yml)
[![Latest tag](https://img.shields.io/github/v/tag/pietercusters/stub-out-claude-md?label=release&color=blue)](https://github.com/pietercusters/stub-out-claude-md/tags)
[![Python](https://img.shields.io/badge/python-3.9%E2%80%933.14-blue?logo=python&logoColor=white)](https://github.com/pietercusters/stub-out-claude-md/blob/main/pyproject.toml)
[![OS](https://img.shields.io/badge/os-linux%20%7C%20macos%20%7C%20windows-lightgrey)](https://github.com/pietercusters/stub-out-claude-md/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/pietercusters/stub-out-claude-md?color=green)](https://github.com/pietercusters/stub-out-claude-md/blob/main/LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

A simple opinionated solution to Anthropic's [stubborn](https://github.com/anthropics/claude-code/issues/6235) [refusal](https://github.com/anthropics/claude-code/issues/31005) to adopt the [AGENTS.md](https://agents.md/) open format.

**`AGENTS.md` is source of truth, `CLAUDE.md` points to it.**

This is a pre-commit hook that enforces this.

</div>

## What it does, in short

Per directory, the hook enforces: either **neither** file exists, or **both**
exist with `AGENTS.md` holding the real content and `CLAUDE.md` being exactly
the stub. It never discards content — it moves, merges, or deduplicates it —
and it converts symlinks into regular files. Works on Linux, macOS, and
Windows.

## Usage

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
-   repo: https://github.com/pietercusters/stub-out-claude-md
    rev: v0.2.0
    hooks:
    -   id: stub-out-claude-md
```

That runs on all changed files. It is recommended to run `pre-commit run stub-out-claude-md --all-files` once locally, and always in CI.

To bump `rev` to the latest release later, run `pre-commit autoupdate`.

## What it does, in more detail

| You have | The hook does |
| --- | --- |
| Only `CLAUDE.md` with content | Moves the content to `AGENTS.md`, replaces `CLAUDE.md` with the stub |
| Only `AGENTS.md` with content | Creates the `CLAUDE.md` stub |
| `CLAUDE.md` symlinked to `AGENTS.md` (or anywhere else) | Replaces the symlink with a regular file, then applies the rules |
| Both files with identical content | Keeps `AGENTS.md`, stubs `CLAUDE.md` |
| Both files with *different* content | Appends the `CLAUDE.md` content to `AGENTS.md` under a `<!-- merged from CLAUDE.md ... -->` marker, then stubs `CLAUDE.md` — review the merge |
| `CLAUDE.md` with the stub *plus* extra lines | Moves the extra lines to `AGENTS.md`, keeps the stub |
| Roles reversed (`AGENTS.md` contains `@CLAUDE.md`) | Swaps them |
| Empty files or stubs pointing at nothing (no real content anywhere) | Deletes the leftovers, restoring the clean "neither exists" state |
| Non-canonical stubs (`@./AGENTS.md`, CRLF, BOM, stray whitespace) | Rewrites the canonical stub `@AGENTS.md` |

It fails with an instruction (instead of fixing) when information could be
lost or judgment is needed: broken symlinks, symlinks to directories, a
directory literally named `CLAUDE.md`, or wrong-case filenames like
`claude.md` (fix with a two-step `git mv`).

Like other formatting hooks, a run that changes files exits non-zero and
shows what it did; review, `git add`, and commit again — the second run
passes. 

## Notes

- The pair is checked in every directory a staged `CLAUDE.md`/`AGENTS.md`
  lives in, at any depth — `@AGENTS.md` imports are relative to the
  importing file.
- pre-commit does not pass **deleted** files to hooks, so "AGENTS.md deleted,
  stale stub left behind" is caught by `pre-commit run --all-files` (e.g. in
  CI), not at commit time.
- On Windows checkouts with `core.symlinks=false`, git materializes symlinks
  as plain text files; the hook detects these via the git index (mode
  `120000`) and converts them too.
- If your repo forces CRLF endings via `.gitattributes`/`core.autocrlf`, add
  `CLAUDE.md text eol=lf` to `.gitattributes` so git doesn't renormalize the
  stub back to CRLF on every commit.
- `CLAUDE.local.md` and `~/.claude/CLAUDE.md` are out of scope.

## Development

The project is managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync          # create .venv with the project + dev dependencies
uv run pytest    # run the unit tests

# end-to-end against a scratch repo:
uv run pre-commit try-repo /path/to/stub-out-claude-md stub-out-claude-md --verbose --all-files
```

Feel free to contribute.

## License

MIT

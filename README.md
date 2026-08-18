# stub-out-claude-md

A [pre-commit](https://pre-commit.com) hook that keeps `AGENTS.md` as the
single source of truth for agent instructions, and `CLAUDE.md` as a stub
containing only `@AGENTS.md` (Claude Code's import syntax).

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
    rev: v0.1.0
    hooks:
    -   id: stub-out-claude-md
```

pre-commit requires `rev` to be an immutable revision (a tag), not a branch
like `main` — hook environments are cached per rev, so a moving ref would
never update anyway. To bump all hooks in your config to their latest tags,
run:

```bash
pre-commit autoupdate
```

## What it does

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
passes. Content moves are byte-exact (non-UTF-8 files included).

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

CI (GitHub Actions) runs the test suite on Linux, macOS, and Windows against
every supported Python version (3.9 through 3.14).

## License

MIT

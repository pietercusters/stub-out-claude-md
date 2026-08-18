"""Keep AGENTS.md as the single source of truth for agent instructions.

Invariant, enforced per directory: either neither AGENTS.md nor CLAUDE.md
exists, or both exist with AGENTS.md holding the real content and CLAUDE.md
containing exactly the Claude Code import stub ``@AGENTS.md``.

The hook never discards user-authored content: it moves, merges, or
deduplicates it. Symlinks are converted into regular files. Anything that
cannot be fixed without losing information fails with an instruction.
"""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

CLAUDE = "CLAUDE.md"
AGENTS = "AGENTS.md"
STUB = b"@AGENTS.md\n"
AGENTS_TOKENS = frozenset({"@AGENTS.md", "@./AGENTS.md"})
CLAUDE_TOKENS = frozenset({"@CLAUDE.md", "@./CLAUDE.md"})
MERGE_MARKER = b"<!-- merged from CLAUDE.md by stub-out-claude-md -->"

# Per-file states after symlink normalization.
ABSENT = "absent"
EMPTY = "empty"  # zero bytes, whitespace-only, or a content-free self-import
STUB_ONLY = "stub"  # CLAUDE.md holding only @AGENTS.md import line(s)
STUB_EXTRA = "stub+extra"  # @AGENTS.md line(s) plus real content
INVERTED = "inverted"  # AGENTS.md holding exactly @CLAUDE.md
REAL = "real"


class Location:
    """One directory holding CLAUDE.md and/or AGENTS.md."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.claude = directory / CLAUDE
        self.agents = directory / AGENTS
        self.fixes: List[str] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []


def _decode(data: bytes) -> Optional[str]:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _classify(path: Path, name: str) -> Tuple[str, bytes, Optional[bytes]]:
    """Return (state, raw bytes, remainder bytes for STUB_EXTRA)."""
    if not path.exists():
        return ABSENT, b"", None
    data = path.read_bytes()
    text = _decode(data)
    if text is None:  # undecodable bytes can never be a stub
        return REAL, data, None
    stripped = text.strip()
    if not stripped:
        return EMPTY, data, None
    if name == CLAUDE:
        if stripped in CLAUDE_TOKENS:  # self-import carries no content
            return EMPTY, data, None
        lines = text.splitlines(keepends=True)
        if any(line.strip() in AGENTS_TOKENS for line in lines):
            rest = "".join(l for l in lines if l.strip() not in AGENTS_TOKENS)
            if not rest.strip():
                return STUB_ONLY, data, None
            return STUB_EXTRA, data, rest.lstrip("\r\n").encode("utf-8")
        return REAL, data, None
    if stripped in CLAUDE_TOKENS:
        return INVERTED, data, None
    if stripped in AGENTS_TOKENS:  # self-import carries no content
        return EMPTY, data, None
    return REAL, data, None


def _git_index_mode(path: Path) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--stage", "--", path.name],
            cwd=str(path.parent),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    lines = proc.stdout.strip().splitlines()
    return lines[0].split()[0] if lines else None


def _normalize(loc: Location, path: Path) -> bool:
    """Turn symlinks into regular files; reject non-files. False on error."""
    if os.path.islink(path):
        target = os.readlink(path)
        resolved = Path(os.path.realpath(path))
        if resolved.is_file():
            data = resolved.read_bytes()
            path.unlink()
            path.write_bytes(data)
            loc.fixes.append(
                f"replaced symlink {path} (-> {target}) with a regular file"
            )
            return True
        if resolved.is_dir():
            loc.errors.append(
                f"{path} is a symlink to a directory (-> {target}); replace it with a file"
            )
        else:
            loc.errors.append(
                f"{path} is a broken symlink (-> {target}); fix or delete it"
            )
        return False
    if not path.exists():
        return True
    if path.is_dir():
        loc.errors.append(f"{path} is a directory; expected a file")
        return False
    if not path.is_file():
        loc.errors.append(f"{path} is not a regular file")
        return False
    if _git_index_mode(path) == "120000":
        # core.symlinks=false checkout: the file's content is the link target.
        text = _decode(path.read_bytes())
        target = (text or "").strip()
        resolved = (path.parent / target) if target else None
        if (
            resolved is not None
            and resolved.is_file()
            and os.path.realpath(resolved) != os.path.realpath(path)
        ):
            path.write_bytes(resolved.read_bytes())
            loc.fixes.append(
                f"materialized git symlink {path} (-> {target}); "
                f"run `git add {path}` so git stores it as a regular file"
            )
        else:
            loc.errors.append(
                f"{path} is a symlink in the git index (-> {target or '?'}) "
                f"whose target cannot be read; fix or delete it"
            )
            return False
    return True


def _case_conflicts(loc: Location) -> bool:
    try:
        entries = os.listdir(loc.dir)
    except OSError as exc:
        loc.errors.append(f"cannot list {loc.dir}: {exc}")
        return True
    expected = {"claude.md": CLAUDE, "agents.md": AGENTS}
    bad = sorted(
        entry
        for entry in entries
        if entry.lower() in expected and entry not in (CLAUDE, AGENTS)
    )
    for entry in bad:
        want = expected[entry.lower()]
        loc.errors.append(
            f"{loc.dir / entry}: wrong-case filename; rename it with "
            f"`git mv {entry} {want}.tmp && git mv {want}.tmp {want}`"
        )
    return bool(bad)


def _ensure_newline(data: bytes) -> bytes:
    return data if data.endswith(b"\n") else data + b"\n"


def _write_stub(loc: Location, message: str) -> None:
    loc.claude.write_bytes(STUB)
    loc.fixes.append(message)


def _apply(loc: Location) -> None:
    c_state, c_data, c_rest = _classify(loc.claude, CLAUDE)
    a_state, a_data, _ = _classify(loc.agents, AGENTS)

    # The bytes representing CLAUDE.md's real (non-stub) content, if any.
    payload = c_data if c_state == REAL else c_rest if c_state == STUB_EXTRA else None

    if a_state == REAL:
        if payload is not None:
            if payload.strip() == a_data.strip():
                _write_stub(
                    loc,
                    f"{loc.claude}: duplicated {loc.agents}; replaced with the stub",
                )
            else:
                merged = (
                    a_data.rstrip(b"\r\n")
                    + b"\n\n"
                    + MERGE_MARKER
                    + b"\n\n"
                    + _ensure_newline(payload)
                )
                loc.agents.write_bytes(merged)
                _write_stub(
                    loc,
                    f"appended {loc.claude} content to {loc.agents} under a merge "
                    f"marker and replaced {loc.claude} with the stub — review the merge",
                )
        elif c_state in (ABSENT, EMPTY):
            _write_stub(loc, f"wrote @AGENTS.md stub to {loc.claude}")
        elif c_state == STUB_ONLY and c_data != STUB:
            _write_stub(loc, f"normalized {loc.claude} stub to canonical @AGENTS.md")
    elif a_state == INVERTED:
        if payload is not None:
            loc.agents.write_bytes(_ensure_newline(payload))
            _write_stub(
                loc,
                f"swapped: moved {loc.claude} content into {loc.agents} "
                f"and replaced {loc.claude} with the stub",
            )
        else:
            _delete_leftovers(loc, c_state, a_state)
    else:  # AGENTS.md absent or empty
        if payload is not None:
            loc.agents.write_bytes(_ensure_newline(payload))
            _write_stub(
                loc,
                f"moved {loc.claude} content to {loc.agents} "
                f"and replaced {loc.claude} with the stub",
            )
        else:
            _delete_leftovers(loc, c_state, a_state)


def _delete_leftovers(loc: Location, c_state: str, a_state: str) -> None:
    """No real content anywhere: restore the clean 'neither exists' state."""
    removed = []
    for path, state in ((loc.claude, c_state), (loc.agents, a_state)):
        if state != ABSENT:
            path.unlink()
            removed.append(str(path))
    if removed:
        loc.fixes.append(
            "deleted content-free leftover(s): " + ", ".join(removed)
        )


def _cycle_warning(loc: Location) -> None:
    if not loc.agents.is_file() or os.path.islink(loc.agents):
        return
    text = _decode(loc.agents.read_bytes())
    if text is None:
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "@CLAUDE.md" in line:
            loc.warnings.append(
                f"{loc.agents} line {lineno} references @CLAUDE.md, which is a "
                f"stub importing AGENTS.md — this is an import cycle"
            )


def _process(loc: Location) -> None:
    if _case_conflicts(loc):
        return
    ok = _normalize(loc, loc.claude)
    ok = _normalize(loc, loc.agents) and ok
    if not ok:
        return
    _apply(loc)
    _cycle_warning(loc)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*", help="staged CLAUDE.md/AGENTS.md paths")
    args = parser.parse_args(argv)

    directories = sorted({Path(name).parent for name in args.filenames}, key=str)
    changed = errored = False
    for directory in directories:
        loc = Location(directory)
        _process(loc)
        for msg in loc.fixes:
            print(f"Fixed: {msg}")
        for msg in loc.warnings:
            print(f"WARNING: {msg}")
        for msg in loc.errors:
            print(f"ERROR: {msg}")
        changed = changed or bool(loc.fixes)
        errored = errored or bool(loc.errors)
    return 1 if changed or errored else 0


if __name__ == "__main__":
    raise SystemExit(main())

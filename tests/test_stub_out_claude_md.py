import os
import shutil
import subprocess
import sys

import pytest

from stub_out_claude_md import MERGE_MARKER, STUB, main


def run(*paths):
    return main([str(p) for p in paths])


def snapshot(root):
    """Map of relative path -> bytes (symlinks recorded as their target)."""
    tree = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            if os.path.islink(path):
                tree[rel] = ("link", os.readlink(path))
            else:
                with open(path, "rb") as f:
                    tree[rel] = ("file", f.read())
    return tree


def assert_idempotent(tmp_path, *paths):
    """A second run must change nothing and exit 0."""
    before = snapshot(tmp_path)
    existing = [p for p in paths if os.path.lexists(p)]
    assert run(*existing) == 0 if existing else True
    assert snapshot(tmp_path) == before


symlinks_supported = pytest.mark.skipif(
    sys.platform == "win32" and not hasattr(os, "symlink"),
    reason="symlinks unavailable",
)


# --- compliant states -------------------------------------------------------

def test_compliant_pair_passes(tmp_path):
    (tmp_path / "AGENTS.md").write_text("real instructions\n")
    (tmp_path / "CLAUDE.md").write_bytes(STUB)
    assert run(tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md") == 0
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB


# --- auto-fix rows ----------------------------------------------------------

def test_writes_stub_when_claude_missing(tmp_path):
    (tmp_path / "AGENTS.md").write_text("real instructions\n")
    assert run(tmp_path / "AGENTS.md") == 1
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB
    assert_idempotent(tmp_path, tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md")


def test_overwrites_empty_claude_with_stub(tmp_path):
    (tmp_path / "AGENTS.md").write_text("real instructions\n")
    (tmp_path / "CLAUDE.md").write_text("   \n\n")
    assert run(tmp_path / "CLAUDE.md") == 1
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB


@pytest.mark.parametrize(
    "variant",
    [b"@AGENTS.md", b"  @AGENTS.md \n\n", b"@./AGENTS.md\n", b"@AGENTS.md\r\n",
     b"\xef\xbb\xbf@AGENTS.md\n"],
)
def test_normalizes_stub_variants(tmp_path, variant):
    (tmp_path / "AGENTS.md").write_text("real instructions\n")
    (tmp_path / "CLAUDE.md").write_bytes(variant)
    assert run(tmp_path / "CLAUDE.md") == 1
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB
    assert_idempotent(tmp_path, tmp_path / "CLAUDE.md")


@pytest.mark.parametrize("agents_pre", [None, b"", b"  \n"])
def test_moves_content_to_agents(tmp_path, agents_pre):
    content = b"# My instructions\n\nDo the thing.\n"
    (tmp_path / "CLAUDE.md").write_bytes(content)
    if agents_pre is not None:
        (tmp_path / "AGENTS.md").write_bytes(agents_pre)
    assert run(tmp_path / "CLAUDE.md") == 1
    assert (tmp_path / "AGENTS.md").read_bytes() == content
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB
    assert_idempotent(tmp_path, tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md")


def test_dedupes_identical_content(tmp_path):
    content = b"# Same everywhere\n"
    (tmp_path / "CLAUDE.md").write_bytes(content)
    (tmp_path / "AGENTS.md").write_bytes(content)
    assert run(tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md") == 1
    assert (tmp_path / "AGENTS.md").read_bytes() == content
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB


def test_merges_conflicting_content_under_marker(tmp_path):
    (tmp_path / "AGENTS.md").write_bytes(b"agents version\n")
    (tmp_path / "CLAUDE.md").write_bytes(b"claude version\n")
    assert run(tmp_path / "CLAUDE.md") == 1
    merged = (tmp_path / "AGENTS.md").read_bytes()
    assert merged.startswith(b"agents version\n")
    assert MERGE_MARKER in merged
    assert merged.endswith(b"claude version\n")
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB
    assert_idempotent(tmp_path, tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md")


def test_stub_plus_extra_moves_remainder(tmp_path):
    (tmp_path / "CLAUDE.md").write_bytes(b"@AGENTS.md\n\nExtra rule\n")
    assert run(tmp_path / "CLAUDE.md") == 1
    assert (tmp_path / "AGENTS.md").read_bytes() == b"Extra rule\n"
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB


def test_stub_plus_extra_appends_to_real_agents(tmp_path):
    (tmp_path / "AGENTS.md").write_bytes(b"agents version\n")
    (tmp_path / "CLAUDE.md").write_bytes(b"@AGENTS.md\nExtra rule\n")
    assert run(tmp_path / "CLAUDE.md") == 1
    merged = (tmp_path / "AGENTS.md").read_bytes()
    assert MERGE_MARKER in merged and merged.endswith(b"Extra rule\n")
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB


@pytest.mark.parametrize(
    "claude_pre,agents_pre",
    [
        (b"@AGENTS.md\n", None),   # stub pointing at nothing
        (b"", None),               # lone empty CLAUDE.md
        (None, b"  \n"),           # lone whitespace AGENTS.md
        (b" \n", b""),             # both empty
        (b"@AGENTS.md\n", b"\n"),  # stub + empty
        (b"@CLAUDE.md\n", None),   # content-free self-import
    ],
)
def test_deletes_content_free_leftovers(tmp_path, claude_pre, agents_pre):
    if claude_pre is not None:
        (tmp_path / "CLAUDE.md").write_bytes(claude_pre)
    if agents_pre is not None:
        (tmp_path / "AGENTS.md").write_bytes(agents_pre)
    assert run(tmp_path / "CLAUDE.md") == 1
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_swaps_inverted_pair(tmp_path):
    (tmp_path / "AGENTS.md").write_bytes(b"@CLAUDE.md\n")
    (tmp_path / "CLAUDE.md").write_bytes(b"the real content\n")
    assert run(tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md") == 1
    assert (tmp_path / "AGENTS.md").read_bytes() == b"the real content\n"
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB


def test_deletes_circular_stub_pair(tmp_path):
    (tmp_path / "AGENTS.md").write_bytes(b"@CLAUDE.md\n")
    (tmp_path / "CLAUDE.md").write_bytes(b"@AGENTS.md\n")
    assert run(tmp_path / "CLAUDE.md") == 1
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_non_utf8_content_moves_byte_exact(tmp_path):
    content = b"\xff\xfe\x00 raw bytes \x80\n"
    (tmp_path / "CLAUDE.md").write_bytes(content)
    assert run(tmp_path / "CLAUDE.md") == 1
    assert (tmp_path / "AGENTS.md").read_bytes() == content
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB


def test_multiple_directories_one_run(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "AGENTS.md").write_text("root\n")
    (tmp_path / "sub" / "CLAUDE.md").write_text("sub content\n")
    assert run(tmp_path / "AGENTS.md", tmp_path / "sub" / "CLAUDE.md") == 1
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB
    assert (tmp_path / "sub" / "AGENTS.md").read_text() == "sub content\n"
    assert (tmp_path / "sub" / "CLAUDE.md").read_bytes() == STUB


# --- warnings ---------------------------------------------------------------

def test_cycle_reference_warns_but_passes(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("see @CLAUDE.md for details\n")
    (tmp_path / "CLAUDE.md").write_bytes(STUB)
    assert run(tmp_path / "CLAUDE.md") == 0
    assert "import cycle" in capsys.readouterr().out


# --- symlinks ---------------------------------------------------------------

@symlinks_supported
def test_sibling_symlink_becomes_stub(tmp_path):
    (tmp_path / "AGENTS.md").write_text("real instructions\n")
    os.symlink("AGENTS.md", tmp_path / "CLAUDE.md")
    assert run(tmp_path / "CLAUDE.md") == 1
    assert not os.path.islink(tmp_path / "CLAUDE.md")
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB
    assert (tmp_path / "AGENTS.md").read_text() == "real instructions\n"
    assert_idempotent(tmp_path, tmp_path / "CLAUDE.md")


@symlinks_supported
def test_external_symlink_is_materialized(tmp_path):
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "common.md").write_text("shared content\n")
    (tmp_path / "proj").mkdir()
    os.symlink(
        os.path.join("..", "shared", "common.md"), tmp_path / "proj" / "CLAUDE.md"
    )
    assert run(tmp_path / "proj" / "CLAUDE.md") == 1
    assert (tmp_path / "proj" / "AGENTS.md").read_text() == "shared content\n"
    assert (tmp_path / "proj" / "CLAUDE.md").read_bytes() == STUB
    # the symlink target itself is untouched
    assert (tmp_path / "shared" / "common.md").read_text() == "shared content\n"


@symlinks_supported
def test_broken_symlink_fails_untouched(tmp_path, capsys):
    os.symlink("does-not-exist.md", tmp_path / "CLAUDE.md")
    assert run(tmp_path / "CLAUDE.md") == 1
    assert os.path.islink(tmp_path / "CLAUDE.md")
    assert "broken symlink" in capsys.readouterr().out


@symlinks_supported
def test_symlink_to_directory_fails(tmp_path, capsys):
    (tmp_path / "somedir").mkdir()
    os.symlink("somedir", tmp_path / "CLAUDE.md")
    assert run(tmp_path / "CLAUDE.md") == 1
    assert os.path.islink(tmp_path / "CLAUDE.md")
    assert "symlink to a directory" in capsys.readouterr().out


# --- hard failures ----------------------------------------------------------

def test_directory_named_claude_md_fails(tmp_path, capsys):
    (tmp_path / "CLAUDE.md").mkdir()
    assert run(tmp_path / "CLAUDE.md") == 1
    assert (tmp_path / "CLAUDE.md").is_dir()
    assert "is a directory" in capsys.readouterr().out


def test_lone_empty_agents_is_deleted(tmp_path):
    (tmp_path / "AGENTS.md").write_bytes(b"")
    assert run(tmp_path / "AGENTS.md") == 1
    assert not (tmp_path / "AGENTS.md").exists()


def test_wrong_case_filename_fails(tmp_path, capsys):
    (tmp_path / "claude.md").write_text("content\n")
    assert run(tmp_path / "claude.md") == 1
    out = capsys.readouterr().out
    assert "wrong-case filename" in out and "git mv" in out
    # nothing was touched
    assert (tmp_path / "claude.md").read_text() == "content\n"


# --- git index mode 120000 (Windows core.symlinks=false simulation) ---------

@pytest.mark.skipif(shutil.which("git") is None, reason="git unavailable")
def test_git_index_symlink_is_materialized(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "AGENTS.md").write_text("real instructions\n")
    # a plain file whose content is the link target, staged with symlink mode
    (tmp_path / "CLAUDE.md").write_bytes(b"AGENTS.md")
    blob = subprocess.run(
        ["git", "hash-object", "-w", "CLAUDE.md"],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    ).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"120000,{blob},CLAUDE.md")

    assert run(tmp_path / "CLAUDE.md") == 1
    assert (tmp_path / "CLAUDE.md").read_bytes() == STUB
    assert (tmp_path / "AGENTS.md").read_text() == "real instructions\n"

"""T3.5: the reproduction checker, exercised without network.

`make reproduce` is the only gate whose subject is the repository itself rather than a
number in it. These tests drive real git repositories in tmp_path, because a mocked
`git status` would assert the parser against the shape the author imagined rather than
the shape git emits, and that shape is the whole subject.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_reproduction
import pytest

#: Pinned here independently of check_reproduction.TRACKED_ARTIFACTS. Parametrizing the
#: dirty-one-path controls over the production constant alone would stay green if an entry
#: were deleted: the loop would simply run one fewer case and report nothing.
EXPECTED_ARTIFACTS = (
    "experiments/swebench/derived/aggregates.json",
    "experiments/swebench/results/results.json",
    "experiments/swebench/results/cards.json",
    "experiments/swebench/results/pairs.csv",
    "experiments/swebench/results/cards.html",
    "README.md",
)


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repository carrying the six tracked artifacts, all committed."""
    git("init", "-q", cwd=tmp_path)
    git("config", "user.email", "test@example.com", cwd=tmp_path)
    git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / ".gitignore").write_text(
        "experiments/swebench/derived/labels.csv\nexperiments/swebench/derived/unevaluated.json\n",
        encoding="utf-8",
    )
    for rel in EXPECTED_ARTIFACTS:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"committed {rel}\n", encoding="utf-8")
    (tmp_path / "source.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "-A", cwd=tmp_path)
    git("commit", "-qm", "fixture", cwd=tmp_path)
    return tmp_path


def test_the_tracked_artifact_list_is_exactly_these_six() -> None:
    """An omitted entry silently shrinks every parametrized control below it."""
    assert tuple(check_reproduction.TRACKED_ARTIFACTS) == EXPECTED_ARTIFACTS


class TestEnvironmentBanner:
    """A local run that reads as canonical evidence is the defect this prevents.

    D0.9 makes only ubuntu-24.04 with Python 3.11.15 canonical. A checker that printed
    nothing about its environment would let a developer paste a green local run into a
    review as though it settled reproduction.
    """

    def test_the_banner_says_the_run_is_not_canonical(self, repo, monkeypatch, capsys) -> None:
        """Asserted on the canonical interpreter too, in the test below, so this cannot
        become conditional on being non-canonical and then vanish where it matters least."""
        monkeypatch.chdir(repo)
        check_reproduction.main(["--preflight"])
        assert "not canonical evidence" in capsys.readouterr().out

    def test_the_banner_appears_even_on_the_canonical_interpreter(
        self, repo, monkeypatch, capsys
    ) -> None:
        """The interpreter alone was never the whole canonical claim: the runner image is
        the other half, so a default-mode run on 3.11.15 is still a development check."""
        monkeypatch.chdir(repo)
        monkeypatch.setattr(check_reproduction, "running_python", lambda: "3.11.15")
        check_reproduction.main(["--preflight"])
        assert "not canonical evidence" in capsys.readouterr().out

    def test_the_banner_names_the_interpreter_and_its_exact_version(
        self, repo, monkeypatch, capsys
    ) -> None:
        monkeypatch.chdir(repo)
        check_reproduction.main(["--preflight"])
        out = capsys.readouterr().out
        assert sys.executable in out
        assert check_reproduction.running_python() in out

    def test_canonical_fails_on_a_non_3_11_15_interpreter(self, repo, monkeypatch, capsys) -> None:
        monkeypatch.chdir(repo)
        monkeypatch.setattr(check_reproduction, "running_python", lambda: "3.11.14")
        assert check_reproduction.main(["--preflight", "--canonical"]) != 0
        assert "3.11.15" in capsys.readouterr().out

    def test_canonical_passes_on_3_11_15(self, repo, monkeypatch) -> None:
        """Patched, so the control runs on any interpreter."""
        monkeypatch.chdir(repo)
        monkeypatch.setattr(check_reproduction, "running_python", lambda: "3.11.15")
        assert check_reproduction.main(["--preflight", "--canonical"]) == 0

    def test_canonical_mode_does_not_disclaim_the_run_it_is_gating(
        self, repo, monkeypatch, capsys
    ) -> None:
        """CI is where the verdict is established, so a canonical run printing "not
        canonical evidence" would contradict the job it is part of, in the job log a
        reader consults to confirm reproduction.
        """
        monkeypatch.chdir(repo)
        monkeypatch.setattr(check_reproduction, "running_python", lambda: "3.11.15")
        check_reproduction.main(["--preflight", "--canonical"])
        out = capsys.readouterr().out
        assert "not canonical evidence" not in out
        assert "canonical interpreter check passed" in out
        assert "runner image is pinned by the workflow" in out


class TestPreflight:
    """A writer that runs on a dirty tree destroys the evidence it should have refused on.

    fetch.py, run.py and report.py --write all overwrite tracked artifacts, so a check
    that ran after them would report a clean tree it had itself created. Ordering is the
    whole guard, and it is asserted against the Makefile text in Task 5: calling the
    checker alone never invokes a writer, so no test here can establish it.
    """

    def test_a_tracked_modification_refuses_to_start(self, repo, monkeypatch, capsys) -> None:
        monkeypatch.chdir(repo)
        (repo / "README.md").write_text("edited\n", encoding="utf-8")

        assert check_reproduction.main(["--preflight"]) != 0
        assert "README.md" in capsys.readouterr().out

    def test_a_staged_change_refuses_to_start(self, repo, monkeypatch, capsys) -> None:
        """Staged is still uncommitted. A guard reading only the unstaged half would let
        `git add` be the way to slip work past it."""
        monkeypatch.chdir(repo)
        (repo / "README.md").write_text("edited\n", encoding="utf-8")
        git("add", "README.md", cwd=repo)

        assert check_reproduction.main(["--preflight"]) != 0
        assert "README.md" in capsys.readouterr().out

    def test_an_untracked_non_ignored_file_refuses_to_start(
        self, repo, monkeypatch, capsys
    ) -> None:
        monkeypatch.chdir(repo)
        (repo / "scratch.md").write_text("notes\n", encoding="utf-8")

        assert check_reproduction.main(["--preflight"]) != 0
        assert "scratch.md" in capsys.readouterr().out

    def test_the_refusal_says_how_to_proceed(self, repo, monkeypatch, capsys) -> None:
        """A developer with real work in progress is told to stash it, rather than
        discovering afterwards that a writer overwrote it."""
        monkeypatch.chdir(repo)
        (repo / "README.md").write_text("edited\n", encoding="utf-8")

        check_reproduction.main(["--preflight"])
        assert "stash" in capsys.readouterr().out

    def test_a_gitignored_file_does_not_block_the_start(self, repo, monkeypatch) -> None:
        """labels.csv and unevaluated.json are rebuilt every run and are gitignored, so
        a guard that refused on them would refuse on every second run."""
        monkeypatch.chdir(repo)
        (repo / "experiments/swebench/derived/labels.csv").write_text(
            "leftover\n", encoding="utf-8"
        )

        assert check_reproduction.main(["--preflight"]) == 0

    def test_a_clean_tree_starts(self, repo, monkeypatch) -> None:
        monkeypatch.chdir(repo)
        assert check_reproduction.main(["--preflight"]) == 0

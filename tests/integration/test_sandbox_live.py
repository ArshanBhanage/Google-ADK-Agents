"""Live sandbox tests. Marked live because they need a container runtime.

These assert the isolation is real rather than declared: no network, an unprivileged
UID, a read-only project mount, and an honest tests_not_run when dependencies are
missing. The fixtures are controlled local code written by these tests, not a mock
provider.
"""

from pathlib import Path

import pytest

from agents.code_reviewer.sandbox import (
    NO_DOCKER,
    UNTRUSTED_PR,
    docker_usable,
    isolation_record,
    run_tests,
)

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
async def runtime() -> None:
    if not await docker_usable():
        pytest.skip("SKIPPED (no container runtime available)")


def write(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body)
    return path


async def test_a_pull_request_is_refused_without_running_anything(tmp_path: Path) -> None:
    # No runtime needed: policy refuses before the container is considered.
    outcome = await run_tests(tmp_path, authorized=False)
    assert outcome.status == "tests_not_run"
    assert outcome.reason == UNTRUSTED_PR
    assert outcome.exit_code is None
    # The controls that would have applied are still documented.
    assert outcome.isolation["network"] == "none"


async def test_passing_tests_are_reported_as_passed(runtime: None, tmp_path: Path) -> None:
    write(
        tmp_path,
        "test_ok.py",
        "import unittest\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_arithmetic(self):\n"
        "        self.assertEqual(2 + 2, 4)\n",
    )
    outcome = await run_tests(tmp_path, authorized=True)
    assert outcome.status == "passed", outcome
    assert outcome.exit_code == 0
    assert outcome.isolation["network"] == "none"


async def test_failing_tests_are_reported_as_failed_not_as_an_error(
    runtime: None, tmp_path: Path
) -> None:
    write(
        tmp_path,
        "test_bad.py",
        "import unittest\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_wrong(self):\n"
        "        self.assertEqual(1, 2)\n",
    )
    outcome = await run_tests(tmp_path, authorized=True)
    assert outcome.status == "failed"
    assert outcome.exit_code not in (None, 0)


async def test_the_sandbox_has_no_network(runtime: None, tmp_path: Path) -> None:
    write(
        tmp_path,
        "test_net.py",
        "import socket, unittest\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_cannot_reach_the_internet(self):\n"
        "        with self.assertRaises(OSError):\n"
        "            socket.create_connection(('1.1.1.1', 53), timeout=3)\n",
    )
    outcome = await run_tests(tmp_path, authorized=True)
    assert outcome.status == "passed", outcome.stdout_tail


async def test_the_sandbox_runs_unprivileged(runtime: None, tmp_path: Path) -> None:
    write(
        tmp_path,
        "test_uid.py",
        "import os, unittest\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_not_root(self):\n"
        "        self.assertNotEqual(os.getuid(), 0)\n",
    )
    outcome = await run_tests(tmp_path, authorized=True)
    assert outcome.status == "passed", outcome.stdout_tail


async def test_the_project_mount_is_read_only(runtime: None, tmp_path: Path) -> None:
    write(
        tmp_path,
        "test_ro.py",
        "import pathlib, unittest\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_cannot_write_into_the_project(self):\n"
        "        with self.assertRaises(OSError):\n"
        "            pathlib.Path('/work/written.txt').write_text('x')\n",
    )
    outcome = await run_tests(tmp_path, authorized=True)
    assert outcome.status == "passed", outcome.stdout_tail
    # And the host directory really is untouched.
    assert not (tmp_path / "written.txt").exists()


async def test_missing_dependencies_are_tests_not_run_rather_than_failed(
    runtime: None, tmp_path: Path
) -> None:
    # A real suite needing third-party packages cannot run without network access, and
    # that is reported as unexecuted rather than as a failing test.
    write(
        tmp_path,
        "test_dep.py",
        "import httpx  # not installed in the sandbox\nimport unittest\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_x(self):\n"
        "        self.assertTrue(httpx)\n",
    )
    outcome = await run_tests(tmp_path, authorized=True)
    assert outcome.status == "tests_not_run"
    assert "no network" in outcome.reason


async def test_no_tests_collected_is_not_a_pass(runtime: None, tmp_path: Path) -> None:
    write(tmp_path, "notes.txt", "nothing to run here")
    outcome = await run_tests(tmp_path, authorized=True)
    assert outcome.status != "passed"


def test_the_isolation_record_names_every_control() -> None:
    record = isolation_record()
    assert record["network"] == "none"
    assert "unprivileged" in record["user"]
    assert record["root_filesystem"] == "read-only"
    assert record["capabilities"] == "all dropped"
    assert NO_DOCKER.startswith("tests_not_run")

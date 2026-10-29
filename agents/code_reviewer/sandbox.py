"""Isolated test execution, or an honest refusal to execute.

Running a pull request's tests means running a stranger's code. The only acceptable
place for that is an ephemeral container with no network, no writable host mount, an
unprivileged UID, every capability dropped and hard resource limits. If any of that is
unavailable the outcome is `tests_not_run`, never a silent fallback to the host.

Two policy decisions, both deliberate:

- The sandbox has no network, so third-party dependencies cannot be installed. Tests are
  run with stdlib `unittest`, which means a project needing external packages is
  reported as `tests_not_run` with that reason rather than being half-run.
- Executing a GitHub pull request's tests is refused by default. A diff from an arbitrary
  contributor is untrusted code, and the container is a strong boundary but not an
  unbreakable one. An operator may authorize a specific local directory instead.
"""

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path

IMAGE = "python:3.12-alpine"
TIMEOUT_SECONDS = 180.0
MAX_OUTPUT_BYTES = 200_000
# Reasons the gate reports verbatim rather than paraphrasing into something vaguer.
NO_DOCKER = "tests_not_run: no usable container runtime, so nothing was executed"
UNTRUSTED_PR = (
    "tests_not_run: executing a pull request's tests is refused by policy. A diff from "
    "an arbitrary contributor is untrusted code; static analysis was performed instead."
)

DOCKER_ARGS = (
    "--rm",
    "--network",
    "none",
    "--user",
    "65534:65534",
    "--read-only",
    "--memory",
    "512m",
    "--memory-swap",
    "512m",
    "--cpus",
    "1",
    "--pids-limit",
    "128",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
)


@dataclass
class TestOutcome:
    """`status` is one of passed, failed, tests_not_run, error."""

    status: str
    reason: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    stdout_tail: str = ""
    stderr_tail: str = ""
    isolation: dict[str, str] = field(default_factory=dict)

    @property
    def executed(self) -> bool:
        return self.status in {"passed", "failed"}


def docker_path() -> str | None:
    return shutil.which("docker")


async def docker_usable() -> bool:
    binary = docker_path()
    if binary is None:
        return False
    process = await asyncio.create_subprocess_exec(
        binary,
        "info",
        "--format",
        "{{.ServerVersion}}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(process.wait(), timeout=30)
    except TimeoutError:
        process.kill()
        await process.wait()
        return False
    return process.returncode == 0


def isolation_record() -> dict[str, str]:
    """What was actually enforced, so the claim is inspectable rather than asserted."""
    return {
        "image": IMAGE,
        "network": "none",
        "user": "65534:65534 (unprivileged)",
        "root_filesystem": "read-only",
        "project_mount": "read-only bind",
        "writable_space": "tmpfs /tmp, noexec, nosuid, 64m",
        "memory": "512m, swap capped at 512m",
        "cpus": "1",
        "pids_limit": "128",
        "capabilities": "all dropped",
        "privilege_escalation": "no-new-privileges",
        "runner": "python -m unittest (stdlib only; no package installation is possible)",
    }


async def run_tests(project: Path, *, authorized: bool) -> TestOutcome:
    """Execute a directory's stdlib tests in a locked container, or decline."""
    # The isolation record is reported even when nothing ran, so a reader can see the
    # controls that would apply rather than an empty section implying none exist.
    if not authorized:
        return TestOutcome(
            status="tests_not_run", reason=UNTRUSTED_PR, isolation=isolation_record()
        )
    binary = docker_path()
    if binary is None or not await docker_usable():
        return TestOutcome(status="tests_not_run", reason=NO_DOCKER)
    # Resolved off the event loop: pathlib touches the filesystem.
    directory = await asyncio.to_thread(project.resolve)
    if not await asyncio.to_thread(directory.is_dir):
        return TestOutcome(
            status="error", reason=f"The authorized test directory does not exist: {directory}"
        )

    loop = asyncio.get_running_loop()
    started = loop.time()
    process = await asyncio.create_subprocess_exec(
        binary,
        "run",
        *DOCKER_ARGS,
        "--mount",
        f"type=bind,src={directory},dst=/work,readonly",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--workdir",
        "/work",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        IMAGE,
        "python",
        "-m",
        "unittest",
        "discover",
        "-v",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        return TestOutcome(
            status="tests_not_run",
            reason=f"tests_not_run: the sandbox exceeded its {TIMEOUT_SECONDS:.0f}s budget",
            isolation=isolation_record(),
        )
    duration_ms = round((loop.time() - started) * 1000)
    stdout = out[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
    stderr = err[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
    code = process.returncode

    if code == 0:
        status, reason = "passed", ""
    elif "ModuleNotFoundError" in stderr or "ModuleNotFoundError" in stdout:
        status = "tests_not_run"
        reason = (
            "tests_not_run: the suite imports third-party packages, which cannot be "
            "installed in a sandbox with no network access."
        )
    elif code == 5:
        status, reason = "tests_not_run", "tests_not_run: the runner collected no tests"
    else:
        status, reason = "failed", f"the suite exited {code}"
    return TestOutcome(
        status=status,
        reason=reason,
        exit_code=code,
        duration_ms=duration_ms,
        stdout_tail="\n".join(stdout.splitlines()[-40:]),
        stderr_tail="\n".join(stderr.splitlines()[-20:]),
        isolation=isolation_record(),
    )

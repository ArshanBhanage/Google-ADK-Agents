"""Safe adapter around the real `gemini` executable.

Behaviour here is pinned to Gemini CLI 0.65.0 and was established by running it, not
by reading documentation:

- `-p/--prompt` selects headless mode; `-o/--output-format json` emits a single object
  with `response`, `session_id` and `stats`, and `error` when it fails.
- Exit 55 means the working directory is not a trusted folder. In that state the CLI
  also *silently downgrades* `--approval-mode plan` back to `default`, so trust must be
  granted explicitly for the read-only policy to hold at all.
- The CLI prefers `GOOGLE_API_KEY`/`GEMINI_API_KEY` when either is present, even with
  `GOOGLE_GENAI_USE_VERTEXAI=true`. With a stray key exported it billed an unrelated
  project and returned 403 BILLING_DISABLED. The child environment is therefore built
  from an allowlist rather than inherited.
"""

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.agent_core.config import ROOT, Settings
from packages.agent_core.provider import Backend, resolve_backend

DEFAULT_EXECUTABLE = ROOT / "infra" / "gemini-cli" / "node_modules" / ".bin" / "gemini"
# Read-only policy. "plan" is the CLI's documented read-only mode; --yolo and
# auto_edit are never used, and the value is not configurable from a request.
APPROVAL_MODE = "plan"
MAX_OUTPUT_BYTES = 1_000_000
TIMEOUT_SECONDS = 180.0
TRUST_REFUSED_EXIT = 55
# Inherited only when already present. Deliberately excludes GOOGLE_API_KEY and
# GEMINI_API_KEY so the child cannot authenticate as a different account.
ENV_ALLOWLIST = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "NODE_OPTIONS", "SSL_CERT_FILE")


class CliError(RuntimeError):
    """The CLI could not be invoked, or did not return a usable result."""


@dataclass(frozen=True)
class CliInvocation:
    """Sanitized record of one subprocess run. Holds no credentials."""

    executable: str
    arguments: list[str]
    workspace: str
    exit_code: int
    duration_ms: int
    stderr_summary: str
    response: str
    session_id: str
    stats: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "executable": self.executable,
            "arguments": self.arguments,
            "workspace": self.workspace,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stderr_summary": self.stderr_summary,
            "response": self.response,
            "session_id": self.session_id,
            "stats": self.stats,
        }


def resolve_executable(settings: Settings | None = None) -> Path:
    """Resolve from trusted configuration, never from a model-supplied value."""
    config = settings or Settings()
    configured = config.gemini_cli_path.strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            raise CliError("GEMINI_CLI_PATH must be an absolute path")
    elif DEFAULT_EXECUTABLE.exists():
        candidate = DEFAULT_EXECUTABLE
    else:
        found = shutil.which("gemini")
        if not found:
            raise CliError(
                "BLOCKED_GEMINI_CLI: no gemini executable. Run `make setup-gemini-cli`, "
                "or set GEMINI_CLI_PATH in the local root .env to an absolute path."
            )
        candidate = Path(found)
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise CliError(f"Configured gemini executable is not a file: {resolved}")
    if not os.access(resolved, os.X_OK):
        raise CliError(f"Configured gemini executable is not executable: {resolved}")
    return resolved


def resolve_workspace(settings: Settings | None = None) -> Path:
    """The single directory the CLI may read. Symlinks are resolved before the check."""
    config = settings or Settings()
    configured = config.gemini_workspace.strip()
    if not configured:
        raise CliError(
            "BLOCKED_GEMINI_WORKSPACE: set GEMINI_WORKSPACE in the local root .env to an "
            "absolute path to a directory you authorize the CLI to read."
        )
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        raise CliError("GEMINI_WORKSPACE must be an absolute path")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise CliError(f"GEMINI_WORKSPACE is not a directory: {resolved}")
    secret = find_secret_file(resolved)
    if secret is not None:
        raise CliError(
            "BLOCKED_GEMINI_WORKSPACE: the workspace contains a credential file "
            f"({secret.name}), and the CLI can read every file in its workspace. "
            "Point GEMINI_WORKSPACE at a subdirectory that holds no secrets."
        )
    ancestor = find_ancestor_env(resolved)
    if ancestor is not None:
        raise CliError(
            "BLOCKED_GEMINI_WORKSPACE: an ancestor directory holds "
            f"{ancestor}, which the CLI loads as project context. Observed: a key in "
            "such a file overrode the Vertex credentials and billed another project. "
            "Choose a workspace with no .env in any parent directory."
        )
    return resolved


def find_ancestor_env(workspace: Path) -> Path | None:
    """The CLI walks upward for a project .env, so ancestors are part of the attack
    surface even though they are outside the workspace itself."""
    for parent in workspace.parents:
        for name in (".env", ".env.local"):
            candidate = parent / name
            if candidate.is_file():
                return candidate
        if parent == parent.parent or parent == Path.home():
            break
    return None


SECRET_NAMES = frozenset({".env", "id_rsa", "id_ed25519", "credentials.json", ".netrc"})
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
SKIP_DIRECTORIES = frozenset({".git", "node_modules", ".venv", "__pycache__", "dist", ".cache"})
WORKSPACE_SCAN_LIMIT = 20_000


def looks_secret(name: str) -> bool:
    if name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES):
        return True
    return name.startswith(".env") and name != ".env.example"


def find_secret_file(workspace: Path) -> Path | None:
    """Refuse a workspace holding credentials, since the CLI can read all of it.

    The scan is bounded and skips vendor directories. Exhausting the budget is treated
    as unverifiable rather than safe, so an enormous tree fails closed.
    """
    seen = 0
    for directory, subdirectories, files in os.walk(workspace):
        subdirectories[:] = [name for name in subdirectories if name not in SKIP_DIRECTORIES]
        for name in files:
            seen += 1
            if looks_secret(name):
                return Path(directory) / name
        if seen > WORKSPACE_SCAN_LIMIT:
            return Path(directory) / "<scan budget exhausted; workspace too large to verify>"
    return None


def child_environment(backend: Backend) -> dict[str, str]:
    """Build the child environment from an allowlist, with no provider key."""
    environment = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    if not backend.uses_vertex:
        raise CliError(
            "BLOCKED_GEMINI_CLI_BACKEND: Part B runs the CLI against Vertex AI so usage "
            "bills the Cloud project. Set GOOGLE_GENAI_USE_VERTEXAI=TRUE in root .env."
        )
    environment["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    environment["GOOGLE_CLOUD_PROJECT"] = backend.project
    environment["GOOGLE_CLOUD_LOCATION"] = backend.location
    # Trust must be explicit, and only ever for the allowlisted workspace. Without it
    # the CLI exits 55 and downgrades the read-only approval mode.
    environment["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
    return environment


def build_arguments(task: str, model: str) -> list[str]:
    """One argv list. The task is a single -p value and never reaches a shell."""
    if not task.strip():
        raise CliError("The CLI task must not be empty")
    if len(task) > 4000:
        raise CliError("The CLI task exceeds the 4000 character limit")
    if any(ord(character) < 32 and character not in "\n\t" for character in task):
        raise CliError("The CLI task contains control characters")
    return ["--approval-mode", APPROVAL_MODE, "-o", "json", "-m", model, "-p", task]


def _summarise(stderr: bytes) -> str:
    lines = [line.strip() for line in stderr.decode("utf-8", "replace").splitlines()]
    informative = [line for line in lines if line and "Ripgrep is not available" not in line]
    return " | ".join(informative[:4])[:600]


def interpret_exit(code: int, stderr_summary: str) -> str:
    if code == TRUST_REFUSED_EXIT:
        return (
            "The CLI refused the workspace as untrusted (exit 55), which also disables "
            "its read-only approval mode. Verify GEMINI_WORKSPACE."
        )
    return f"The CLI exited {code}. {stderr_summary}".strip()


async def run_cli(task: str, *, settings: Settings | None = None) -> CliInvocation:
    """Invoke the real executable once, bounded in time and output."""
    config = settings or Settings()
    executable = resolve_executable(config)
    workspace = resolve_workspace(config)
    backend = resolve_backend(config)
    arguments = build_arguments(task, backend.model)

    loop = asyncio.get_running_loop()
    started = loop.time()
    process = await asyncio.create_subprocess_exec(
        str(executable),
        *arguments,
        cwd=str(workspace),
        env=child_environment(backend),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        # start_new_session put the child in its own process group, so the whole tree
        # is signalled rather than leaving orphaned helpers behind.
        try:
            os.killpg(process.pid, 9)
        except (ProcessLookupError, PermissionError):
            process.kill()
        await process.wait()
        raise CliError(f"The CLI exceeded its {TIMEOUT_SECONDS:.0f}s budget") from None

    duration_ms = round((loop.time() - started) * 1000)
    stderr_summary = _summarise(stderr)
    if len(stdout) > MAX_OUTPUT_BYTES:
        raise CliError("The CLI produced more output than the configured limit")
    if process.returncode != 0:
        raise CliError(interpret_exit(process.returncode or -1, stderr_summary))
    return parse_output(
        stdout,
        executable=str(executable),
        arguments=arguments,
        workspace=str(workspace),
        exit_code=process.returncode,
        duration_ms=duration_ms,
        stderr_summary=stderr_summary,
    )


def parse_output(
    stdout: bytes,
    *,
    executable: str,
    arguments: list[str],
    workspace: str,
    exit_code: int,
    duration_ms: int,
    stderr_summary: str,
) -> CliInvocation:
    """Parse the documented JSON shape, rejecting anything else rather than guessing."""
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CliError("The CLI did not return parseable JSON on stdout") from exc
    if not isinstance(payload, dict):
        raise CliError("The CLI returned JSON that is not an object")
    if payload.get("error"):
        raise CliError(f"The CLI reported an error: {str(payload['error'])[:400]}")
    response = payload.get("response")
    if not isinstance(response, str) or not response.strip():
        raise CliError("The CLI returned no response text")
    stats = payload.get("stats")
    return CliInvocation(
        executable=executable,
        # The task text is replaced so a prompt is never echoed into a trace or log.
        arguments=[*arguments[:-1], "<task>"],
        workspace=workspace,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stderr_summary=stderr_summary,
        response=response,
        session_id=str(payload.get("session_id", "")),
        stats=stats if isinstance(stats, dict) else {},
    )


async def cli_version(settings: Settings | None = None) -> str:
    """Readiness probe. Runs the executable but makes no model call."""
    executable = resolve_executable(settings)
    process = await asyncio.create_subprocess_exec(
        str(executable),
        "--version",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
    if process.returncode != 0:
        raise CliError(f"`gemini --version` exited {process.returncode}")
    return stdout.decode("utf-8", "replace").strip()

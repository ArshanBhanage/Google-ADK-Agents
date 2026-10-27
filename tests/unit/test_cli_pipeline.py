"""B2 tests: pipeline shape and the deterministic grounding check."""

from pathlib import Path

import pytest
from google.adk.agents import LlmAgent
from pydantic import ValidationError

from agents.gemini_cli_tool.agent import root_agent
from agents.gemini_cli_tool.grounding import check_grounding, extract_paths, resolve_within
from agents.gemini_cli_tool.models import CliRequest
from agents.gemini_cli_tool.run import STAGE_KINDS


def workspace(tmp_path: Path) -> Path:
    (tmp_path / "packages" / "agent_core").mkdir(parents=True)
    (tmp_path / "packages" / "agent_core" / "config.py").write_text("x = 1\n")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "main.py").write_text("y = 2\n")
    return tmp_path


def test_pipeline_separates_planning_from_subprocess_execution() -> None:
    pipeline = root_agent.tools[0].agent
    names = [agent.name for agent in pipeline.sub_agents]
    assert names == ["cli_planner", "cli_executor", "cli_grounding", "cli_synthesiser"]
    planner, executor, verifier, _ = pipeline.sub_agents
    # The planner must not be able to touch the workspace.
    assert not planner.tools
    # Exactly one stage owns the subprocess.
    assert [tool.__name__ for tool in executor.tools] == ["inspect_workspace_with_gemini_cli"]
    # Verification must not be delegated to a model.
    assert not isinstance(verifier, LlmAgent)
    assert STAGE_KINDS[verifier.name] == "adk_deterministic_agent"


def test_question_is_bounded_and_required() -> None:
    with pytest.raises(ValidationError):
        CliRequest(question="too short")
    with pytest.raises(ValidationError):
        CliRequest(question="x" * 2001)
    with pytest.raises(ValidationError):
        CliRequest.model_validate({"question": "a valid question here", "extra": 1})
    assert CliRequest(question="  what does api/main.py expose?  ").question.endswith("?")


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("See `api/main.py` and packages/agent_core/config.py.", 2),
        ("No files mentioned at all.", 0),
        ("Look at main.py, config.py and main.py again.", 2),
    ],
)
def test_path_extraction_is_deduplicated(answer: str, expected: int) -> None:
    assert len(extract_paths(answer)) == expected


def test_claims_outside_the_workspace_are_refused(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    for escape in ("/etc/passwd", "../../etc/passwd", "packages/../../secret.py"):
        assert resolve_within(root, escape) is None


def test_a_grounded_answer_is_accepted(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    verdict = check_grounding(
        "The settings live in packages/agent_core/config.py and the app in api/main.py.", root
    )
    assert verdict.grounded is True
    assert set(verdict.paths_present) == {"packages/agent_core/config.py", "api/main.py"}
    assert verdict.paths_absent == []
    # Even a clean pass states what was not verified.
    assert any("contents is not" in line for line in verdict.limitations)


def test_invented_paths_are_reported_and_sink_the_verdict(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    verdict = check_grounding(
        "Configuration is split between api/main.py and services/billing/engine.py.", root
    )
    assert verdict.grounded is False
    assert verdict.paths_present == ["api/main.py"]
    assert verdict.paths_absent == ["services/billing/engine.py"]
    assert any("do not exist" in line for line in verdict.limitations)


def test_a_bare_filename_is_located_and_reported_with_its_real_path(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    verdict = check_grounding("The entry point is main.py.", root)
    # Resolved to where the file actually is, rather than echoed back bare.
    assert verdict.paths_present == ["api/main.py"]
    assert verdict.grounded is True


def test_an_answer_naming_nothing_is_not_treated_as_grounded(tmp_path: Path) -> None:
    verdict = check_grounding("The project looks well organised.", workspace(tmp_path))
    assert verdict.grounded is False
    assert verdict.paths_claimed == []
    assert any("named no file" in line for line in verdict.limitations)


def test_absolute_paths_inside_the_workspace_are_verified_not_failed(tmp_path: Path) -> None:
    """Regression: the CLI reports absolute paths on some runs.

    An earlier extractor sliced an absolute path at a mid-path segment, producing a
    relative path that did not exist, so four real files were reported absent and a
    correct answer was discredited.
    """
    root = workspace(tmp_path)
    answer = (
        f"Settings live in {root}/packages/agent_core/config.py "
        f"and the routes in {root}/api/main.py."
    )
    claimed = extract_paths(answer)
    assert all(claim.startswith("/") for claim in claimed), claimed

    verdict = check_grounding(answer, root)
    assert verdict.grounded is True
    assert verdict.paths_absent == []
    # Reported back workspace-relative, so host paths are not echoed to the user.
    assert set(verdict.paths_present) == {"packages/agent_core/config.py", "api/main.py"}


def test_an_absolute_path_outside_the_workspace_is_still_refused(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    other = tmp_path.parent / "elsewhere.py"
    other.write_text("x = 1\n")
    verdict = check_grounding(f"See {other} for details.", root)
    assert verdict.paths_present == []
    assert verdict.paths_absent == [str(other)]
    assert verdict.grounded is False


def test_the_same_file_named_twice_in_two_forms_counts_once(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    verdict = check_grounding(f"Both api/main.py and {root}/api/main.py are the same module.", root)
    assert verdict.paths_present == ["api/main.py"]

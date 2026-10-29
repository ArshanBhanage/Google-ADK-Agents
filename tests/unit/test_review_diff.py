"""D1 tests: diff parsing, line mapping and finding admissibility. No network calls."""

import pytest

from agents.code_reviewer.analysis import (
    TEST_FILE_EXEMPT_RULES,
    admissible_rule,
    is_test_file,
    severity_for,
    syntax_findings,
)
from agents.code_reviewer.diff import FileDiff, build_file_diff, parse_patch, safe_path

PATCH = """@@ -1,4 +1,6 @@
 import os
+import sys
 
-def old():
+def new():
+    return sys.argv
     return os.getcwd()
@@ -20,2 +22,3 @@ def tail():
 keep
+added_at_23
 keep
"""


def test_only_added_lines_are_recorded_with_new_side_numbers() -> None:
    added, ranges = parse_patch(PATCH)
    assert added[2] == "import sys"
    assert added[4] == "def new():"
    assert added[5] == "    return sys.argv"
    assert added[23] == "added_at_23"
    # Context and removed lines are not claimed as added.
    assert 1 not in added
    assert ranges == [(1, 6), (22, 24)]


def test_removed_lines_do_not_advance_the_new_side_counter() -> None:
    # A patch that only deletes must not shift the numbering of what follows.
    added, _ = parse_patch("@@ -1,3 +1,2 @@\n keep\n-gone\n+replaced\n")
    assert added == {2: "replaced"}


def test_a_no_newline_marker_advances_nothing() -> None:
    added, _ = parse_patch("@@ -1 +1,2 @@\n a\n+b\n\\ No newline at end of file\n")
    assert added == {2: "b"}


def test_a_missing_patch_is_reported_rather_than_treated_as_empty() -> None:
    diff = build_file_diff({"filename": "logo.png", "status": "modified", "additions": 0})
    assert diff.patch_present is False
    assert diff.added_lines == {}
    assert diff.in_diff(1) is False


@pytest.mark.parametrize(
    ("line", "inside"),
    [(1, True), (6, True), (7, False), (21, False), (22, True), (24, True), (25, False)],
)
def test_only_lines_inside_a_hunk_may_be_commented_on(line: int, inside: bool) -> None:
    # This is the guard that stops a review commenting on untouched code.
    diff = build_file_diff({"filename": "a.py", "status": "modified", "patch": PATCH})
    assert diff.in_diff(line) is inside


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("a/b.py", "python"),
        ("web/src/app.tsx", "typescript"),
        ("infra/x.yaml", "yaml"),
        ("Makefile", "other"),
        ("bin/run.sh", "shell"),
    ],
)
def test_language_detection_drives_what_can_be_analysed(path: str, language: str) -> None:
    assert build_file_diff({"filename": path, "status": "modified"}).language == language


@pytest.mark.parametrize(
    "path",
    ["../escape.py", "/etc/passwd", "a/../../b.py", "", "win\\path.py", "~/secrets.py"],
)
def test_unsafe_paths_from_the_api_are_refused(path: str) -> None:
    assert safe_path(path) is False


@pytest.mark.parametrize("path", ["a.py", "src/pkg/mod.py", "web/src/x.tsx"])
def test_ordinary_paths_are_accepted(path: str) -> None:
    assert safe_path(path) is True


def test_a_syntax_error_is_critical_and_located() -> None:
    diff = build_file_diff({"filename": "broken.py", "status": "added", "patch": PATCH})
    (finding,) = syntax_findings("broken.py", "def f(:\n    pass\n", diff)
    assert finding.severity == "critical"
    assert finding.source == "python-ast"
    assert finding.line >= 1


def test_valid_python_produces_no_syntax_finding() -> None:
    diff = build_file_diff({"filename": "ok.py", "status": "added", "patch": PATCH})
    assert syntax_findings("ok.py", "def f():\n    return 1\n", diff) == []


@pytest.mark.parametrize(
    ("rule", "severity"),
    [
        ("E902", "critical"),
        ("F821", "high"),
        ("S608", "high"),
        ("B008", "medium"),
        ("ASYNC101", "high"),
        ("E501", "low"),
        ("UP045", "low"),
        ("ZZ999", "medium"),
    ],
)
def test_severity_is_derived_from_the_rule_family(rule: str, severity: str) -> None:
    assert severity_for(rule) == severity


@pytest.mark.parametrize(
    "path",
    ["tests/unit/test_a.py", "src/tests/helpers.py", "pkg/test_mod.py", "pkg/mod_test.py"],
)
def test_test_files_are_recognised(path: str) -> None:
    assert is_test_file(path) is True


def test_application_files_are_not_mistaken_for_tests() -> None:
    assert is_test_file("src/pkg/latest.py") is False
    assert is_test_file("src/contest/mod.py") is False


@pytest.mark.parametrize("rule", sorted(TEST_FILE_EXEMPT_RULES))
def test_assert_and_friends_are_not_defects_in_a_test_file(rule: str) -> None:
    # Reporting `assert` in a test suite would show the review does not understand
    # what it is reading.
    assert admissible_rule(rule, "tests/unit/test_a.py") is False
    assert admissible_rule(rule, "src/pkg/mod.py") is True


def test_real_rules_are_still_reported_in_test_files() -> None:
    assert admissible_rule("F821", "tests/unit/test_a.py") is True


def test_the_file_diff_contract_is_stable() -> None:
    diff = FileDiff(path="a.py", status="modified", additions=1, deletions=0)
    assert diff.language == "python"
    assert diff.in_diff(1) is False

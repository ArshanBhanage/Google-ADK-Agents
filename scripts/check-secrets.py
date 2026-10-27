import re
import subprocess
import sys
from pathlib import Path

from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings

# Recorded evidence pins each citation to the SHA-256 of the public page body that was
# actually fetched. Those digests are the proof the gate rests on, not credentials, and
# detect-secrets reports them as high-entropy hex. The exemption is deliberately narrow:
# only under docs/evidence/, only this plugin, and only a 64-hex value on a *sha256 key.
PUBLISHED_DIGEST = re.compile(r'"[a-z_]*sha256"\s*:\s*"[0-9a-f]{64}"')
DIGEST_PLUGIN = "Hex High Entropy String"


def is_published_digest(root: Path, filename: str, line_number: int) -> bool:
    path = Path(filename)
    if "docs/evidence" not in path.as_posix():
        return False
    try:
        line = (root / path).read_text().splitlines()[line_number - 1]
    except (OSError, IndexError, UnicodeDecodeError):
        return False
    return bool(PUBLISHED_DIGEST.search(line))


root = Path(__file__).resolve().parents[1]
paths = (
    subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    )
    .decode()
    .split("\0")
)
failures = []
with default_settings():
    collection = SecretsCollection()
    for name in filter(None, paths):
        path = Path(name)
        if (
            path.name == ".env"
            or (path.name.startswith(".env.") and path.name != ".env.example")
            or path.suffix in {".pem", ".key"}
        ):
            failures.append(name + ": forbidden secret file")
        if (root / path).is_file():
            collection.scan_file(str(root / path))
    exempt = 0
    for filename, secrets in collection.data.items():
        relative = str(Path(filename).relative_to(root))
        for secret in secrets:
            if secret.type == DIGEST_PLUGIN and is_published_digest(
                root, relative, secret.line_number
            ):
                exempt += 1
                continue
            failures.append(relative + ":" + str(secret.line_number) + ": " + secret.type)
for failure in failures:
    print(failure)
print(
    f"Secret checks: {len(failures)} findings; {exempt} published page digests "
    "exempted; values never displayed"
)
sys.exit(bool(failures))

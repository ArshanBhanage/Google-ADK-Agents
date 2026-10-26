import subprocess
import sys
from pathlib import Path

from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings

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
    for filename, secrets in collection.data.items():
        for secret in secrets:
            failures.append(
                str(Path(filename).relative_to(root))
                + ":"
                + str(secret.line_number)
                + ": "
                + secret.type
            )
for failure in failures:
    print(failure)
print(f"Secret checks: {len(failures)} findings; values never displayed")
sys.exit(bool(failures))

import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

# Directories that are never worth walking into: dependencies, build output,
# and VCS internals. Skipping them early is what keeps indexing a real
# frontend repo from taking forever parsing someone else's node_modules.
SKIP_DIRECTORIES = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "venv",
    ".venv",
    "__pycache__",
    "vendor",
    "target",
}


@contextmanager
def cloned_repo(github_url: str, access_token: str | None = None):
    """
    Shallow-clones a repo into a temp directory and cleans it up afterward.
    A depth-1 clone only, we only need the current state of the default
    branch to index it, not its history.

    Public repos clone anonymously. Private repos need the token embedded
    in the URL, since a plain `git clone` has no login prompt to answer.

    Known limitation: embedding the token in the URL means it appears in
    this process's argument list, visible to other processes on the same
    machine via `ps`. Acceptable for a single-user local tool; a real
    multi-tenant deployment should use a git credential helper instead.
    """
    clone_url = github_url
    if access_token:
        parsed = urlparse(github_url)
        clone_url = parsed._replace(netloc=f"{access_token}@{parsed.netloc}").geturl()

    tmp_dir = tempfile.mkdtemp(prefix="pr-reviewer-index-")
    try:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", clone_url, tmp_dir],
                check=True,
                capture_output=True,
                timeout=300,
            )
        except subprocess.CalledProcessError as exc:
            # Re-raise without the original exception, whose command list
            # (and therefore the access token embedded in clone_url) would
            # otherwise end up in logs or an API error response.
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            raise RuntimeError(f"git clone failed for {github_url}: {stderr}") from None
        yield Path(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def walk_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        yield path

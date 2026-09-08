"""
Gives the agent's read tools access to real file contents.

The index stores where a symbol is, not what it says, so reading requires a
checkout. One shallow clone is made per review and reused for every read,
rather than cloning per tool call.
"""

import logging
from contextlib import contextmanager
from pathlib import Path

from app.indexing.git import cloned_repo

logger = logging.getLogger("agent.source")

# A guard against a tool call trying to read an enormous file into the prompt.
MAX_READ_LINES = 400


class RepositorySource:
    def __init__(self, root: Path):
        self.root = root

    def _resolve(self, path: str) -> Path | None:
        """
        Resolve inside the clone only. The path comes from model output, so
        `../../etc/passwd` has to be impossible even though the clone is
        temporary and the model is not adversarial by design.
        """
        candidate = (self.root / path).resolve()
        try:
            candidate.relative_to(self.root.resolve())
        except ValueError:
            logger.warning("rejected path outside the repository: %r", path)
            return None
        return candidate if candidate.is_file() else None

    def read_lines(self, path: str, start_line: int | None, end_line: int | None) -> str | None:
        resolved = self._resolve(path)
        if resolved is None:
            return None
        try:
            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None

        start = max(1, start_line or 1)
        end = min(len(lines), end_line or len(lines))
        if end < start:
            return None
        end = min(end, start + MAX_READ_LINES - 1)

        # Numbered so the model can cite a line it actually saw.
        width = len(str(end))
        return "\n".join(
            f"{number:>{width}}| {text}"
            for number, text in enumerate(lines[start - 1 : end], start=start)
        )

    def list_files(self, prefix: str = "", limit: int = 100) -> list[str]:
        results: list[str] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or ".git" in path.parts:
                continue
            relative = str(path.relative_to(self.root))
            if prefix and not relative.startswith(prefix):
                continue
            results.append(relative)
            if len(results) >= limit:
                break
        return results


@contextmanager
def repository_source(github_url: str, access_token: str | None = None):
    """Clone once for the life of a review, clean up afterwards."""
    with cloned_repo(github_url, access_token) as root:
        logger.info("source checkout ready at %s", root)
        yield RepositorySource(root)

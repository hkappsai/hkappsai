import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import update_github_stats as updater


def repository(
    name: str,
    *,
    commits: int = 1,
    fork: bool = False,
    archived: bool = False,
    pushed_at: str = "2026-09-01T00:00:00Z",
) -> dict:
    return {
        "name": name,
        "url": f"https://github.com/hkappsai/{name}",
        "isArchived": archived,
        "isFork": fork,
        "stargazerCount": 2,
        "forkCount": 1,
        "pushedAt": pushed_at,
        "primaryLanguage": {"name": "Python"},
        "issues": {"totalCount": 3},
        "defaultBranchRef": {"target": {"history": {"totalCount": commits}}},
    }


class StatsTests(unittest.TestCase):
    def test_render_excludes_forks_and_archived_repositories(self) -> None:
        stats = updater.render_stats(
            [repository("active", commits=7), repository("fork", fork=True), repository("old", archived=True)],
            now=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )

        self.assertIn("| **1** | **7** | **2** | **1** | **3** | **1** |", stats)
        self.assertIn("[active](https://github.com/hkappsai/active)", stats)
        self.assertNotIn("github.com/hkappsai/fork", stats)
        self.assertNotIn("github.com/hkappsai/old", stats)

    def test_update_readme_changes_only_marker_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readme.md"
            path.write_text(
                f"before\n{updater.START_MARKER}\nold\n{updater.END_MARKER}\nafter\n",
                encoding="utf-8",
            )

            self.assertTrue(updater.update_readme(path, "new stats"))
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                f"before\n{updater.START_MARKER}\n\nnew stats\n\n{updater.END_MARKER}\nafter\n",
            )
            self.assertFalse(updater.update_readme(path, "new stats"))


if __name__ == "__main__":
    unittest.main()

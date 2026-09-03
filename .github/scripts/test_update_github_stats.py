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
    private: bool = False,
    language: str = "Python",
    color: str = "#3572A5",
    pushed_at: str = "2026-09-01T00:00:00Z",
) -> dict:
    return {
        "name": name,
        "url": f"https://github.com/hkappsai/{name}",
        "isArchived": archived,
        "isFork": fork,
        "isPrivate": private,
        "stargazerCount": 2,
        "forkCount": 1,
        "pushedAt": pushed_at,
        "primaryLanguage": {"name": language},
        "languages": {
            "edges": [{"size": 100, "node": {"name": language, "color": color}}]
        },
        "issues": {"totalCount": 3},
        "defaultBranchRef": {"target": {"history": {"totalCount": commits}}},
    }


class StatsTests(unittest.TestCase):
    def test_query_requests_only_owned_repositories(self) -> None:
        captured_query = ""

        def fake_graphql(_token: str, query: str, _variables: dict) -> dict:
            nonlocal captured_query
            captured_query = query
            return {
                "repositoryOwner": {
                    "repositories": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }

        original_graphql = updater.graphql
        updater.graphql = fake_graphql
        try:
            self.assertEqual(updater.get_repositories("token", "hkappsai"), [])
        finally:
            updater.graphql = original_graphql

        self.assertIn("ownerAffiliations: [OWNER]", captured_query)
        self.assertNotIn("privacy: PUBLIC", captured_query)

    def test_technology_uses_public_and_private_repository_languages(self) -> None:
        technology = updater.render_technology(
            [
                repository("public-python"),
                repository("private-kotlin", private=True, language="Kotlin", color="#A97BFF"),
            ]
        )

        self.assertIn("![Python]", technology)
        self.assertIn("![Kotlin]", technology)

    def test_render_excludes_forks_and_archived_repositories(self) -> None:
        stats = updater.render_stats(
            [
                repository("active", commits=7),
                repository("private", private=True),
                repository("fork", fork=True),
                repository("old", archived=True),
            ],
            now=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )

        self.assertIn("| **1** | **7** | **2** | **1** | **3** | **1** |", stats)
        self.assertIn("[active](https://github.com/hkappsai/active)", stats)
        self.assertNotIn("github.com/hkappsai/private", stats)
        self.assertNotIn("github.com/hkappsai/fork", stats)
        self.assertNotIn("github.com/hkappsai/old", stats)

    def test_update_readme_changes_only_marker_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readme.md"
            path.write_text(
                f"before\n{updater.TECH_START_MARKER}\nold tech\n"
                f"{updater.TECH_END_MARKER}\nmiddle\n{updater.START_MARKER}\nold stats\n"
                f"{updater.END_MARKER}\nafter\n",
                encoding="utf-8",
            )

            self.assertTrue(updater.update_readme(path, "new tech", "new stats"))
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                f"before\n{updater.TECH_START_MARKER}\n\nnew tech\n\n"
                f"{updater.TECH_END_MARKER}\nmiddle\n{updater.START_MARKER}\n\nnew stats\n\n"
                f"{updater.END_MARKER}\nafter\n",
            )
            self.assertFalse(updater.update_readme(path, "new tech", "new stats"))


if __name__ == "__main__":
    unittest.main()

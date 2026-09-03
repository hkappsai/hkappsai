#!/usr/bin/env python3
"""Update the generated GitHub Activity block in the profile README."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API_URL = "https://api.github.com/graphql"
START_MARKER = "<!-- GITHUB-STATS:START -->"
END_MARKER = "<!-- GITHUB-STATS:END -->"


def graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "hkapps-profile-readme-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the GitHub API: {error.reason}") from error

    if result.get("errors"):
        messages = "; ".join(error.get("message", str(error)) for error in result["errors"])
        raise RuntimeError(f"GitHub GraphQL error: {messages}")

    return result["data"]


def get_repositories(token: str, owner: str) -> list[dict[str, Any]]:
    query = """
    query($login: String!, $cursor: String) {
      repositoryOwner(login: $login) {
        repositories(
          first: 100
          after: $cursor
          privacy: PUBLIC
          orderBy: {field: PUSHED_AT, direction: DESC}
        ) {
          pageInfo { hasNextPage endCursor }
          nodes {
            name
            url
            isArchived
            isFork
            stargazerCount
            forkCount
            pushedAt
            primaryLanguage { name }
            issues(states: OPEN) { totalCount }
            defaultBranchRef {
              target {
                ... on Commit { history { totalCount } }
              }
            }
          }
        }
      }
    }
    """

    repositories: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        data = graphql(token, query, {"login": owner, "cursor": cursor})
        repository_owner = data.get("repositoryOwner")
        if repository_owner is None:
            raise RuntimeError(f"GitHub owner not found: {owner}")

        page = repository_owner["repositories"]
        repositories.extend(repo for repo in page["nodes"] if repo is not None)
        if not page["pageInfo"]["hasNextPage"]:
            return repositories
        cursor = page["pageInfo"]["endCursor"]


def commit_count(repository: dict[str, Any]) -> int:
    try:
        return int(repository["defaultBranchRef"]["target"]["history"]["totalCount"])
    except (KeyError, TypeError, ValueError):
        return 0


def render_stats(repositories: list[dict[str, Any]], now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    active_repositories = [
        repository
        for repository in repositories
        if not repository["isFork"] and not repository["isArchived"]
    ]
    active_cutoff = now - timedelta(days=30)
    recently_active = []
    for repository in active_repositories:
        pushed_at = repository.get("pushedAt")
        if pushed_at:
            pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            if pushed >= active_cutoff:
                recently_active.append(repository)

    languages = Counter(
        repository["primaryLanguage"]["name"]
        for repository in active_repositories
        if repository.get("primaryLanguage")
    )
    top_repositories = sorted(
        active_repositories,
        key=lambda repository: (
            -repository["stargazerCount"],
            -repository["forkCount"],
            -commit_count(repository),
            repository["name"].casefold(),
        ),
    )[:6]

    lines = [
        "| Repositories | Commits | Stars | Forks | Open Issues | Active 30d |",
        "|:------------:|:-------:|:-----:|:-----:|:-----------:|:----------:|",
        (
            f"| **{len(active_repositories):,}** "
            f"| **{sum(commit_count(repo) for repo in active_repositories):,}** "
            f"| **{sum(repo['stargazerCount'] for repo in active_repositories):,}** "
            f"| **{sum(repo['forkCount'] for repo in active_repositories):,}** "
            f"| **{sum(repo['issues']['totalCount'] for repo in active_repositories):,}** "
            f"| **{len(recently_active):,}** |"
        ),
    ]

    if languages:
        lines.extend(["", "### Languages", ""])
        lines.append(" · ".join(f"`{language}`" for language, _ in languages.most_common(8)))

    if top_repositories:
        lines.extend(
            [
                "",
                "### Top Repositories",
                "",
                "| Repository | Stars | Forks | Commits | Language |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for repository in top_repositories:
            language = (repository.get("primaryLanguage") or {}).get("name", "—")
            lines.append(
                f"| [{repository['name']}]({repository['url']}) "
                f"| ⭐ {repository['stargazerCount']:,} "
                f"| {repository['forkCount']:,} "
                f"| {commit_count(repository):,} "
                f"| {language} |"
            )

    if recently_active:
        lines.extend(["", "### Recently Active", ""])
        lines.append(
            " · ".join(
                f"[`{repository['name']}`]({repository['url']})"
                for repository in recently_active[:10]
            )
        )

    lines.extend(
        [
            "",
            f"<sub>Last synced from GitHub: {now.strftime('%d %b %Y %H:%M UTC')}</sub>",
        ]
    )
    return "\n".join(lines)


def update_readme(readme_path: Path, stats: str) -> bool:
    readme = readme_path.read_text(encoding="utf-8")
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise RuntimeError("README must contain exactly one matching pair of GitHub stats markers")

    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER, start)
    updated = f"{readme[:start]}\n\n{stats}\n\n{readme[end:]}"
    if updated == readme:
        return False
    readme_path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    owner = os.environ.get("GITHUB_OWNER")
    readme_path = Path(os.environ.get("README_PATH", "readme.md"))
    if not token or not owner:
        print("GITHUB_TOKEN and GITHUB_OWNER are required", file=sys.stderr)
        return 2

    repositories = get_repositories(token, owner)
    stats = render_stats(repositories)
    changed = update_readme(readme_path, stats)
    print(
        f"Found {len(repositories)} public repositories for {owner}; "
        f"README {'updated' if changed else 'already current'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

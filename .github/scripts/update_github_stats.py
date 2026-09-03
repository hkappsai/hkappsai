#!/usr/bin/env python3
"""Update generated Technology and GitHub Activity blocks in the profile README."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API_URL = "https://api.github.com/graphql"
START_MARKER = "<!-- GITHUB-STATS:START -->"
END_MARKER = "<!-- GITHUB-STATS:END -->"
TECH_START_MARKER = "<!-- GITHUB-TECH:START -->"
TECH_END_MARKER = "<!-- GITHUB-TECH:END -->"

CATEGORY_ORDER = ("Mobile", "Web & Games", "AI & Backend", "Infrastructure")
LANGUAGE_CATEGORIES = {
    "Kotlin": "Mobile",
    "Java": "Mobile",
    "Swift": "Mobile",
    "Dart": "Mobile",
    "Objective-C": "Mobile",
    "Objective-C++": "Mobile",
    "JavaScript": "Web & Games",
    "TypeScript": "Web & Games",
    "HTML": "Web & Games",
    "CSS": "Web & Games",
    "SCSS": "Web & Games",
    "Vue": "Web & Games",
    "Svelte": "Web & Games",
    "GDScript": "Web & Games",
    "C#": "Web & Games",
    "C++": "Web & Games",
    "GLSL": "Web & Games",
    "HLSL": "Web & Games",
    "WebAssembly": "Web & Games",
    "Python": "AI & Backend",
    "Jupyter Notebook": "AI & Backend",
    "Go": "AI & Backend",
    "Rust": "AI & Backend",
    "PHP": "AI & Backend",
    "Ruby": "AI & Backend",
    "C": "AI & Backend",
    "R": "AI & Backend",
    "Scala": "AI & Backend",
    "Clojure": "AI & Backend",
    "Elixir": "AI & Backend",
    "Erlang": "AI & Backend",
    "Julia": "AI & Backend",
    "Lua": "AI & Backend",
    "Shell": "Infrastructure",
    "Dockerfile": "Infrastructure",
    "HCL": "Infrastructure",
    "Nix": "Infrastructure",
    "Makefile": "Infrastructure",
    "CMake": "Infrastructure",
    "PowerShell": "Infrastructure",
    "Batchfile": "Infrastructure",
}
LANGUAGE_LOGOS = {
    "C#": "csharp",
    "C++": "cplusplus",
    "Dockerfile": "docker",
    "HCL": "terraform",
    "Jupyter Notebook": "jupyter",
    "Objective-C": "apple",
    "Objective-C++": "apple",
    "Shell": "gnubash",
}


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
          ownerAffiliations: [OWNER]
          orderBy: {field: PUSHED_AT, direction: DESC}
        ) {
          pageInfo { hasNextPage endCursor }
          nodes {
            name
            url
            isArchived
            isFork
            isPrivate
            stargazerCount
            forkCount
            pushedAt
            primaryLanguage { name }
            languages(first: 50, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name color } }
            }
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


def get_technology_repositories(token: str, owner: str) -> list[dict[str, Any]]:
    """Return language data for every owned repository visible to the token."""
    query = """
    query($login: String!, $cursor: String) {
      repositoryOwner(login: $login) {
        repositories(
          first: 100
          after: $cursor
          ownerAffiliations: [OWNER]
          orderBy: {field: PUSHED_AT, direction: DESC}
        ) {
          pageInfo { hasNextPage endCursor }
          nodes {
            isArchived
            isFork
            languages(first: 50, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name color } }
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


def render_badge(language: str, color: str | None) -> str:
    label = language.replace("-", "--").replace("_", "__").replace(" ", "_")
    encoded_label = urllib.parse.quote(label, safe="")
    badge_color = (color or "555555").lstrip("#")
    logo = LANGUAGE_LOGOS.get(language, language.casefold().replace(" ", ""))
    logo_parameter = f"&logo={urllib.parse.quote(logo, safe='')}" if logo else ""
    logo_color = "black" if badge_color.upper() in {"F1E05A", "F7DF1E"} else "white"
    return (
        f"![{language}](https://img.shields.io/badge/{encoded_label}-{badge_color}"
        f"?style=flat-square{logo_parameter}&logoColor={logo_color})"
    )


def render_technology(repositories: list[dict[str, Any]]) -> str:
    language_totals: Counter[str] = Counter()
    language_colors: dict[str, str | None] = {}
    for repository in repositories:
        if repository["isFork"] or repository["isArchived"]:
            continue
        for edge in (repository.get("languages") or {}).get("edges", []):
            language = edge["node"]["name"]
            language_totals[language] += edge["size"]
            language_colors.setdefault(language, edge["node"].get("color"))

    categories: dict[str, list[str]] = {category: [] for category in CATEGORY_ORDER}
    for language, _ in language_totals.most_common():
        category = LANGUAGE_CATEGORIES.get(language, "AI & Backend")
        categories[category].append(render_badge(language, language_colors[language]))

    lines: list[str] = []
    for category in CATEGORY_ORDER:
        if lines:
            lines.append("")
        lines.extend([f"**{category}**", ""])
        lines.append(" ".join(categories[category]) or "_No languages detected yet._")
    return "\n".join(lines)


def render_stats(repositories: list[dict[str, Any]], now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    active_repositories = [
        repository
        for repository in repositories
        if not repository["isPrivate"]
        and not repository["isFork"]
        and not repository["isArchived"]
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


def replace_block(document: str, start_marker: str, end_marker: str, content: str) -> str:
    if document.count(start_marker) != 1 or document.count(end_marker) != 1:
        raise RuntimeError(f"README must contain exactly one marker pair: {start_marker}")
    start = document.index(start_marker) + len(start_marker)
    end = document.index(end_marker, start)
    return f"{document[:start]}\n\n{content}\n\n{document[end:]}"


def update_readme(readme_path: Path, technology: str, stats: str) -> bool:
    readme = readme_path.read_text(encoding="utf-8")
    updated = replace_block(readme, TECH_START_MARKER, TECH_END_MARKER, technology)
    updated = replace_block(updated, START_MARKER, END_MARKER, stats)
    if updated == readme:
        return False
    readme_path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    technology_token = os.environ.get("TECHNOLOGY_TOKEN") or token
    owner = os.environ.get("GITHUB_OWNER")
    readme_path = Path(os.environ.get("README_PATH", "readme.md"))
    if not token or not owner:
        print("GITHUB_TOKEN and GITHUB_OWNER are required", file=sys.stderr)
        return 2

    public_repositories = get_repositories(token, owner)
    technology_repositories = get_technology_repositories(technology_token, owner)
    technology = render_technology(technology_repositories)
    stats = render_stats(public_repositories)
    changed = update_readme(readme_path, technology, stats)
    print(f"README {'updated' if changed else 'already current'} for {owner}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

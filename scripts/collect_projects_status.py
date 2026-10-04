"""Read GitHub metadata and milestones; publish JSON only after full validation."""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DataError(ValueError):
    pass


PRIORITIES = {"PRIMARY": 0, "NEXT": 1, "INCUBATING": 2}
PHASES = {"DISCOVERY", "DEVELOPMENT"}
FIELDS = ("Project", "Target", "Priority", "Phase")
VALUE_FRAGMENT = """
  ... on ProjectV2ItemFieldTextValue { text }
  ... on ProjectV2ItemFieldSingleSelectValue { name }
"""
PROJECTS_QUERY = """
query($owner: String!, $cursor: String) {
  user(login: $owner) {
    projectsV2(first: 100, after: $cursor) {
      nodes { id title url closed }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""
ITEMS_QUERY = """
query($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        nodes {
          isArchived
          %s
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
""" % "\n".join(
    f'{field.lower()}: fieldValueByName(name: "{field}") {{ {VALUE_FRAGMENT} }}'
    for field in FIELDS
)


def require(condition, message):
    if not condition:
        raise DataError(message)


def connection_pages(fetch):
    """Paginate GraphQL connections, rejecting incomplete or looping cursors."""
    cursor = None
    seen = set()
    nodes = []
    while True:
        page = fetch(cursor)
        require(isinstance(page, dict), "Missing GraphQL connection")
        require(isinstance(page.get("nodes"), list), "Missing GraphQL nodes")
        require(all(isinstance(n, dict) for n in page["nodes"]), "Unreadable GraphQL node")
        nodes.extend(page["nodes"])
        info = page.get("pageInfo", {})
        require(isinstance(info.get("hasNextPage"), bool), "Missing pagination state")
        if not info["hasNextPage"]:
            return nodes
        cursor = info.get("endCursor")
        require(isinstance(cursor, str) and cursor and cursor not in seen,
                "Invalid pagination cursor")
        seen.add(cursor)


def field_text(value):
    if value is None:
        return ""
    require(isinstance(value, dict), "Invalid Project field")
    text = value.get("text", value.get("name"))
    require(isinstance(text, str), "Project fields must be text or single select")
    return text.strip()


def connection_from(data, parent, field):
    node = data.get(parent)
    require(isinstance(node, dict), f"Missing or inaccessible GraphQL {parent}")
    return node.get(field)


def github_url(url):
    require(isinstance(url, str) and re.fullmatch(r"https://github\.com/[\w./%-]+", url),
            "Invalid GitHub source URL")
    return url


def validate_config(config):
    require(isinstance(config, dict), "Invalid configuration")
    require(isinstance(config.get("owner"), str)
            and re.fullmatch(r"[A-Za-z0-9-]+", config["owner"]), "Invalid owner")
    require(isinstance(config.get("project_title"), str) and config["project_title"].strip(),
            "Missing Project title")
    projects = config.get("projects")
    require(isinstance(projects, list) and projects, "Missing configured projects")
    aliases = set()
    for project in projects:
        require(isinstance(project, dict), "Invalid configured project")
        values = project.get("project_values")
        require(isinstance(values, list) and values, "Missing Project field values")
        for value in values:
            require(isinstance(value, str) and value.strip() == value and value,
                    "Invalid Project field value")
            require(value not in aliases, "Duplicate Project field value")
            aliases.add(value)
        repo = project.get("repository")
        require(repo is None or (isinstance(repo, str) and re.fullmatch(
            r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo)), "Invalid repository")
        targets = project.get("targets")
        require(isinstance(targets, dict), "Missing target configuration")
        for target, identifiers in targets.items():
            require(isinstance(target, str) and target.strip(), "Invalid target")
            require(isinstance(identifiers, list) and identifiers, "Empty target milestones")
            require(all(isinstance(m, str) and re.fullmatch(r"M\d{2,}", m)
                        for m in identifiers), "Invalid milestone identifier")
            require(len(set(identifiers)) == len(identifiers), "Duplicate target milestone")
    return config


def build_status(config, items, milestones_by_repository, source_url, updated_at):
    validate_config(config)
    require(isinstance(items, list), "Invalid Project items")
    records = []
    for configured in config["projects"]:
        matches = []
        for item in items:
            require(isinstance(item, dict), "Invalid Project item")
            require(isinstance(item.get("isArchived"), bool), "Missing archive state")
            if item["isArchived"]:
                continue
            if field_text(item.get("project")) in configured["project_values"]:
                matches.append(item)
        label = configured["project_values"][0]
        require(len(matches) == 1, f"Expected one active Project item for {label}; found {len(matches)}")
        item = matches[0]
        metadata = {field: field_text(item.get(field.lower())) for field in FIELDS}
        require(metadata["Priority"] in PRIORITIES, f"Invalid Priority for {label}")
        require(metadata["Phase"] in PHASES, f"Invalid Phase for {label}")
        target = metadata["Target"]
        repo = configured["repository"]
        record = {
            "project": metadata["Project"],
            "priority": metadata["Priority"],
            "phase": metadata["Phase"],
            "target": target or None,
            "repository_url": f"https://github.com/{repo}" if repo else None,
            "progress": None,
            "current_milestone": None,
        }
        if metadata["Phase"] == "DEVELOPMENT":
            require(repo is not None, f"Missing repository for {label}")
            require(target in configured["targets"], f"Unconfigured target for {label}: {target}")
            identifiers = configured["targets"][target]
            milestones = milestones_by_repository.get(repo)
            require(isinstance(milestones, list), f"Missing milestones for {repo}")
            selected = []
            for identifier in identifiers:
                matches = [m for m in milestones if isinstance(m, dict)
                           and isinstance(m.get("title"), str)
                           and re.match(rf"^{re.escape(identifier)}(?:\s|$)", m["title"])]
                require(len(matches) == 1,
                        f"Expected one {identifier} milestone in {repo}; found {len(matches)}")
                milestone = matches[0]
                require(milestone.get("state") in {"open", "closed"}, "Invalid milestone state")
                github_url(milestone.get("html_url"))
                selected.append(milestone)
            closed = sum(m["state"] == "closed" for m in selected)
            total = len(selected)
            record["progress"] = {
                "closed": closed, "total": total,
                "percent": (closed * 100 + total // 2) // total,
            }
            current = next((m for m in selected if m["state"] == "open"), None)
            if current:
                record["current_milestone"] = {
                    "title": current["title"], "url": current["html_url"],
                }
        records.append(record)
    priorities = [record["priority"] for record in records]
    require(len(priorities) == len(set(priorities)), "Duplicate portfolio priority")
    require(set(priorities) == set(PRIORITIES), "Portfolio must include PRIMARY, NEXT and INCUBATING")
    records.sort(key=lambda record: PRIORITIES[record["priority"]])
    return {
        "schema_version": 1,
        "updated_at": updated_at,
        "source": {"title": config["project_title"], "url": github_url(source_url)},
        "projects": records,
    }


class GitHub:
    def __init__(self, token):
        require(bool(token), "Set PORTFOLIO_READ_TOKEN to a classic PAT with read:project")
        self.token = token

    def request(self, url, body=None, authenticated=True):
        require(url.startswith("https://api.github.com/"), "Invalid GitHub API URL")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "portfolio-status",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise DataError(f"GitHub API returned HTTP {error.code}; check access and rate limits") from None
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise DataError(f"GitHub API request failed ({type(error).__name__})") from None

    def graphql(self, query, variables):
        result = self.request("https://api.github.com/graphql",
                              {"query": query, "variables": variables})
        require(isinstance(result, dict) and not result.get("errors")
                and isinstance(result.get("data"), dict), "GitHub GraphQL returned errors or missing data")
        return result["data"]

    def project(self, config):
        projects = connection_pages(lambda cursor: connection_from(self.graphql(
            PROJECTS_QUERY, {"owner": config["owner"], "cursor": cursor}
        ), "user", "projectsV2"))
        matches = [p for p in projects if p.get("title") == config["project_title"]
                   and p.get("closed") is False]
        require(len(matches) == 1, "Expected exactly one open Engineering Portfolio Project")
        project = matches[0]
        items = connection_pages(lambda cursor: connection_from(self.graphql(
            ITEMS_QUERY, {"id": project["id"], "cursor": cursor}
        ), "node", "items"))
        return project["url"], items

    def milestones(self, repository):
        results = []
        page = 1
        while True:
            # Public repository reads need no extra PAT scope.
            batch = self.request(
                f"https://api.github.com/repos/{repository}/milestones?state=all&per_page=100&page={page}",
                authenticated=False,
            )
            require(isinstance(batch, list), "Invalid milestones API response")
            results.extend(batch)
            if len(batch) < 100:
                return results
            page += 1


def collect(config, github):
    validate_config(config)
    source_url, items = github.project(config)
    repositories = {}
    for project in config["projects"]:
        active = [item for item in items if not item.get("isArchived")
                  and field_text(item.get("project")) in project["project_values"]]
        if any(field_text(item.get("phase")) == "DEVELOPMENT" for item in active):
            repository = project["repository"]
            require(repository is not None, "Development project needs a repository")
            if repository not in repositories:
                repositories[repository] = github.milestones(repository)
    return build_status(config, items, repositories, source_url,
                        datetime.now(timezone.utc).isoformat(timespec="seconds"))


def write_status(path, status):
    """Atomic replacement prevents partial output or damage to a valid snapshot."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(status, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="portfolio-status.config.json")
    parser.add_argument("--output", default="projects-status.json")
    args = parser.parse_args()
    token = os.environ.get("PORTFOLIO_READ_TOKEN", "")
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        status = collect(config, GitHub(token))
        require(not token or token not in json.dumps(status, ensure_ascii=False),
                "Credential detected in public output; refusing to publish")
        write_status(args.output, status)
    except (DataError, OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        message = str(error).replace(token, "[REDACTED]") if token else str(error)
        print(f"Portfolio collection failed: {message}", file=sys.stderr)
        return 1
    print(f"Generated {args.output} from GitHub ({len(status['projects'])} projects)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

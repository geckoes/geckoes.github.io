import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts.collect_projects_status import (
    DataError, GitHub, build_status, collect, connection_pages, main, validate_config, write_status,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "portfolio-status.config.json").read_text())


def fixture_items():
    """Acceptance metadata supplied by the user, not a live Project snapshot."""
    return [
        {"isArchived": False, "project": {"text": name}, "priority": {"name": priority},
         "phase": {"name": phase}, "target": {"text": target} if target else None}
        for name, priority, phase, target in [
            ("Temperature Monitor", "PRIMARY", "DEVELOPMENT", "v1.0 Portfolio Release"),
            ("Expected Run", "NEXT", "DISCOVERY", "MVP"),
            ("Air Quality Intelligence", "INCUBATING", "DISCOVERY", None),
        ]
    ]


def fixture_milestones():
    # Titles/states checked against the public API on 2026-10-04.
    titles = ["Core Backend Foundation", "Pagination & Ordering", "API Robustness",
              "Sensor Domain", "Operability", "Reproducible Environment",
              "Demo & API Documentation", "Deployment & Release"]
    return [{"title": f"M{i:02} — {title}", "state": "closed" if i < 2 else "open",
             "html_url": f"https://github.com/geckoes/temperature-monitor/milestone/{i+1}"}
            for i, title in enumerate(titles)]


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.config = copy.deepcopy(CONFIG)
        self.items = fixture_items()
        self.milestones = fixture_milestones()

    def build(self):
        return build_status(self.config, self.items,
                            {"geckoes/temperature-monitor": self.milestones},
                            "https://github.com/users/geckoes/projects/999",
                            "2026-10-04T19:00:00+00:00")

    def test_acceptance_status(self):
        projects = self.build()["projects"]
        primary, next_project, incubating = projects
        self.assertEqual(primary["project"], "Temperature Monitor")
        self.assertEqual((primary["priority"], primary["phase"], primary["target"]),
                         ("PRIMARY", "DEVELOPMENT", "v1.0 Portfolio Release"))
        self.assertEqual(primary["progress"], {"closed": 2, "total": 8, "percent": 25})
        self.assertEqual(primary["current_milestone"]["title"], "M02 — API Robustness")
        self.assertEqual((next_project["priority"], next_project["phase"], next_project["target"]),
                         ("NEXT", "DISCOVERY", "MVP"))
        self.assertEqual((incubating["priority"], incubating["phase"]),
                         ("INCUBATING", "DISCOVERY"))
        for project in projects[1:]:
            self.assertIsNone(project["progress"])
            self.assertIsNone(project["current_milestone"])

    def test_progress_advances_with_api_state(self):
        self.milestones[2]["state"] = "closed"
        primary = self.build()["projects"][0]
        self.assertEqual(primary["progress"], {"closed": 3, "total": 8, "percent": 38})
        self.assertEqual(primary["current_milestone"]["title"], "M03 — Sensor Domain")

    def test_target_membership_ignores_unrelated_milestones_and_api_order(self):
        self.milestones.reverse()
        self.milestones.append({"title": "M08 — Future release", "state": "closed"})
        self.milestones.append({"title": "M020 — Different milestone", "state": "closed"})
        self.assertEqual(self.build()["projects"][0]["progress"]["percent"], 25)
        self.assertEqual(self.build()["projects"][0]["current_milestone"]["title"],
                         "M02 — API Robustness")

    def test_all_closed(self):
        for milestone in self.milestones:
            milestone["state"] = "closed"
        primary = self.build()["projects"][0]
        self.assertEqual(primary["progress"]["percent"], 100)
        self.assertIsNone(primary["current_milestone"])

    def test_all_open(self):
        for milestone in self.milestones:
            milestone["state"] = "open"
        primary = self.build()["projects"][0]
        self.assertEqual(primary["progress"]["percent"], 0)
        self.assertEqual(primary["current_milestone"]["title"], "M00 — Core Backend Foundation")

    def test_missing_or_duplicate_milestone_fails(self):
        for milestones in [self.milestones[:-1], self.milestones + [self.milestones[2]]]:
            with self.subTest(milestones=len(milestones)), self.assertRaises(DataError):
                build_status(self.config, self.items, {"geckoes/temperature-monitor": milestones},
                             "https://github.com/users/geckoes/projects/999", "2026-10-04")

    def test_duplicate_config_identifier_fails(self):
        self.config["projects"][0]["targets"]["v1.0 Portfolio Release"].append("M02")
        with self.assertRaises(DataError):
            validate_config(self.config)

    def test_missing_or_duplicate_project_fails(self):
        for items in [self.items[:-1], self.items + [self.items[0]]]:
            self.items = items
            with self.subTest(count=len(items)), self.assertRaises(DataError):
                self.build()

    def test_archived_items_are_ignored(self):
        archived = copy.deepcopy(self.items[0])
        archived["isArchived"] = True
        self.items.append(archived)
        self.assertEqual(len(self.build()["projects"]), 3)

    def test_metadata_remains_sourced_from_project(self):
        self.items[1]["target"] = {"text": "MVP revised"}
        self.assertEqual(self.build()["projects"][1]["target"], "MVP revised")

    def test_invalid_metadata_fails(self):
        for field, value in [("priority", {"name": "URGENT"}), ("phase", None),
                             ("target", {"text": "Unknown release"})]:
            with self.subTest(field=field):
                items = fixture_items()
                items[0][field] = value
                with self.assertRaises(DataError):
                    build_status(self.config, items, {"geckoes/temperature-monitor": self.milestones},
                                 "https://github.com/users/geckoes/projects/999", "2026-10-04")

    def test_duplicate_priority_fails(self):
        self.items[1]["priority"] = {"name": "PRIMARY"}
        with self.assertRaises(DataError):
            self.build()

    def test_invalid_milestone_state_or_url_fails(self):
        for field, value in [("state", "unknown"), ("html_url", "javascript:alert(1)")]:
            with self.subTest(field=field):
                self.milestones = fixture_milestones()
                self.milestones[0][field] = value
                with self.assertRaises(DataError):
                    self.build()

    def test_only_development_repositories_are_queried(self):
        class FakeGitHub:
            def project(api, config):
                return "https://github.com/users/geckoes/projects/999", self.items

            def milestones(api, repository):
                self.assertEqual(repository, "geckoes/temperature-monitor")
                return self.milestones

        self.assertEqual(collect(self.config, FakeGitHub())["projects"][0]["progress"]["percent"], 25)

    def test_collector_failure_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "projects-status.json"
            output.write_text("previous valid deployment\n")
            result = subprocess.run(
                [sys.executable, "scripts/collect_projects_status.py", "--output", str(output)],
                cwd=ROOT, env={"PORTFOLIO_READ_TOKEN": ""}, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("read:project", result.stderr)
            self.assertEqual(output.read_text(), "previous valid deployment\n")

    def test_atomic_snapshot_write(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "projects-status.json"
            write_status(output, self.build())
            self.assertEqual(json.loads(output.read_text()), self.build())
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_api_or_incoherent_data_preserves_snapshot_before_deploy(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "projects-status.json"
            previous = json.dumps(self.build())
            output.write_text(previous)
            args = ["collector", "--config", str(ROOT / "portfolio-status.config.json"),
                    "--output", str(output)]
            for failure in ["api", "missing-milestone"]:
                with self.subTest(failure=failure), patch("sys.argv", args), patch(
                        "scripts.collect_projects_status.GitHub") as github, patch("sys.stderr"):
                    if failure == "api":
                        github.return_value.project.side_effect = DataError("GitHub API returned HTTP 403")
                    else:
                        github.return_value.project.return_value = (
                            "https://github.com/users/geckoes/projects/999", self.items)
                        github.return_value.milestones.return_value = self.milestones[:-1]
                    self.assertEqual(main(), 1)
                    self.assertEqual(output.read_text(), previous)

    def test_secret_is_excluded_from_json_and_logs(self):
        # Synthetic credential: never use a real PAT in test fixtures.
        sentinel = "synthetic-portfolio-secret-do-not-publish"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "projects-status.json"
            args = ["collector", "--config", str(ROOT / "portfolio-status.config.json"),
                    "--output", str(output)]
            items = fixture_items()
            # Unrelated API properties must not enter the public allowlist.
            items[0]["Authorization"] = sentinel
            items[0]["token"] = sentinel
            with patch("sys.argv", args), patch.dict("os.environ", {"PORTFOLIO_READ_TOKEN": sentinel}), patch(
                    "scripts.collect_projects_status.GitHub") as github, patch(
                    "sys.stdout", new_callable=io.StringIO) as stdout, patch(
                    "sys.stderr", new_callable=io.StringIO) as stderr:
                github.return_value.project.return_value = (
                    "https://github.com/users/geckoes/projects/999", items)
                github.return_value.milestones.return_value = self.milestones
                self.assertEqual(main(), 0)
                self.assertNotIn(sentinel, output.read_text())
                self.assertNotIn(sentinel, stdout.getvalue() + stderr.getvalue())

    def test_reflected_secret_fails_without_replacing_snapshot_or_logging_secret(self):
        sentinel = "synthetic-portfolio-secret-do-not-publish"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "projects-status.json"
            output.write_text("previous valid snapshot")
            args = ["collector", "--config", str(ROOT / "portfolio-status.config.json"),
                    "--output", str(output)]
            for phase in ["DISCOVERY", "DEVELOPMENT"]:
                output.write_text("previous valid snapshot")
                items = fixture_items()
                item = items[1] if phase == "DISCOVERY" else items[0]
                item["target"] = {"text": sentinel}
                with self.subTest(phase=phase), patch("sys.argv", args), patch.dict(
                        "os.environ", {"PORTFOLIO_READ_TOKEN": sentinel}), patch(
                        "scripts.collect_projects_status.GitHub") as github, patch(
                        "sys.stderr", new_callable=io.StringIO) as stderr:
                    github.return_value.project.return_value = (
                        "https://github.com/users/geckoes/projects/999", items)
                    github.return_value.milestones.return_value = self.milestones
                    self.assertEqual(main(), 1)
                    self.assertEqual(output.read_text(), "previous valid snapshot")
                    self.assertNotIn(sentinel, stderr.getvalue())


class ApiTests(unittest.TestCase):
    def test_project_discovery_and_items_use_only_existing_fields(self):
        api = GitHub("test-only-token")
        with patch.object(api, "graphql", side_effect=[
            {"user": {"projectsV2": {"nodes": [
                {"id": "fixture-node", "title": "Engineering Portfolio", "closed": False,
                 "url": "https://github.com/users/geckoes/projects/999"}],
                "pageInfo": {"hasNextPage": False}}}},
            {"node": {"items": {"nodes": fixture_items(),
                                "pageInfo": {"hasNextPage": False}}}},
        ]) as graphql:
            source, items = api.project(CONFIG)
            self.assertEqual(len(items), 3)
            self.assertEqual(source, "https://github.com/users/geckoes/projects/999")
            item_query = graphql.call_args.args[0]
            for field in ["Project", "Target", "Priority", "Phase"]:
                self.assertIn(f'fieldValueByName(name: "{field}")', item_query)
            self.assertNotIn("mutation", item_query)

    def test_inaccessible_project_and_duplicate_title_fail(self):
        api = GitHub("test-only-token")
        responses = [
            {"user": None},
            {"user": {"projectsV2": {"nodes": [], "pageInfo": {"hasNextPage": False}}}},
            {"user": {"projectsV2": {"nodes": [
                {"title": "Engineering Portfolio", "closed": False}] * 2,
                "pageInfo": {"hasNextPage": False}}}},
        ]
        for response in responses:
            with self.subTest(response=response), patch.object(api, "graphql", return_value=response):
                with self.assertRaises(DataError):
                    api.project(CONFIG)

    def test_graphql_pagination(self):
        cursors = []

        def fetch(cursor):
            cursors.append(cursor)
            return {"nodes": [{"page": 1 if cursor is None else 2}],
                    "pageInfo": {"hasNextPage": cursor is None, "endCursor": "next"}}

        self.assertEqual(len(connection_pages(fetch)), 2)
        self.assertEqual(cursors, [None, "next"])

    def test_repeating_cursor_fails(self):
        with self.assertRaises(DataError):
            connection_pages(lambda cursor: {"nodes": [], "pageInfo": {
                "hasNextPage": True, "endCursor": "same"}})

    def test_rest_pagination(self):
        api = GitHub("test-only-token")
        with patch.object(api, "request", side_effect=[[{}] * 100, [{"title": "M100"}]]) as request:
            self.assertEqual(len(api.milestones("geckoes/temperature-monitor")), 101)
            self.assertIn("state=all", request.call_args_list[0].args[0])
            self.assertIn("page=2", request.call_args_list[1].args[0])
            self.assertFalse(request.call_args.kwargs["authenticated"])

    def test_graphql_errors_fail_even_with_partial_data(self):
        api = GitHub("test-only-token")
        with patch.object(api, "request", return_value={"data": {}, "errors": [{"message": "Denied"}]}):
            with self.assertRaises(DataError):
                api.graphql("query", {})

    def test_http_and_network_failures_do_not_leak_token(self):
        api = GitHub("secret-test-value")
        errors = [HTTPError("https://api.github.com/graphql", 403, "Denied", {}, None),
                  URLError("secret-test-value"), TimeoutError()]
        for error in errors:
            with self.subTest(error=type(error).__name__), patch(
                    "scripts.collect_projects_status.urlopen", side_effect=error):
                with self.assertRaises(DataError) as raised:
                    api.graphql("query", {})
                self.assertNotIn(api.token, str(raised.exception))


if __name__ == "__main__":
    unittest.main()

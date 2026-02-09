"""Tests for the web dashboard API."""

import os
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from work_orchestrator.core import projects as projects_mod
from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.db.engine import init_db
from work_orchestrator.web.app import create_app


@pytest.fixture
def web_env():
    """Set up a temp environment for web API testing."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        env = {"WO_DB_PATH": str(db_path), "WO_REPO_PATH": tmp}
        old_env = {}
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v

        # Seed data
        db = init_db(db_path)
        projects_mod.create_project(db, "demo", "Demo Project", tmp)
        tasks_mod.create_task(db, "Setup database", "demo", description="Create tables")
        tasks_mod.create_task(db, "Build API", "demo", depends_on=["setup-database"])
        tasks_mod.create_task(db, "Write tests", "demo")
        tasks_mod.update_task_status(db, "setup-database", "done")
        tasks_mod.update_task_status(db, "build-api", "in-progress")
        tasks_mod.update_task_pr_url(db, "build-api", "https://github.com/user/repo/pull/42")
        # Add subtask
        tasks_mod.create_task(db, "Auth endpoint", "demo", parent_task_id="build-api")
        db.close()

        app = create_app()
        client = TestClient(app)
        yield client

        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestDashboardPage:
    def test_index_returns_html(self, web_env):
        resp = web_env.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Work Orchestrator" in resp.text


class TestProjectsAPI:
    def test_list_projects(self, web_env):
        resp = web_env.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["id"] == "demo"

    def test_get_project(self, web_env):
        resp = web_env.get("/api/projects/demo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Demo Project"

    def test_get_nonexistent_project(self, web_env):
        resp = web_env.get("/api/projects/nope")
        assert resp.status_code == 404


class TestTasksAPI:
    def test_project_tasks(self, web_env):
        resp = web_env.get("/api/projects/demo/tasks")
        assert resp.status_code == 200
        tasks = resp.json()
        # Should only have top-level tasks
        ids = [t["id"] for t in tasks]
        assert "setup-database" in ids
        assert "build-api" in ids
        assert "write-tests" in ids
        # auth-endpoint should be a subtask of build-api, not top-level
        assert "auth-endpoint" not in ids

    def test_project_tasks_nested_subtasks(self, web_env):
        resp = web_env.get("/api/projects/demo/tasks")
        tasks = resp.json()
        build_api = next(t for t in tasks if t["id"] == "build-api")
        assert "subtasks" in build_api
        assert len(build_api["subtasks"]) == 1
        assert build_api["subtasks"][0]["id"] == "auth-endpoint"

    def test_task_has_pr_url(self, web_env):
        resp = web_env.get("/api/projects/demo/tasks")
        tasks = resp.json()
        build_api = next(t for t in tasks if t["id"] == "build-api")
        assert build_api["pr_url"] == "https://github.com/user/repo/pull/42"

    def test_task_has_depends_on(self, web_env):
        resp = web_env.get("/api/projects/demo/tasks")
        tasks = resp.json()
        build_api = next(t for t in tasks if t["id"] == "build-api")
        assert "setup-database" in build_api["depends_on"]

    def test_project_summary(self, web_env):
        resp = web_env.get("/api/projects/demo/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 4  # 3 top-level + 1 subtask
        assert data["counts"]["done"] == 1
        assert data["counts"]["in-progress"] == 1
        assert data["progress_pct"] == 25.0

    def test_get_single_task(self, web_env):
        resp = web_env.get("/api/tasks/build-api")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Build API"
        assert data["pr_url"] == "https://github.com/user/repo/pull/42"
        assert "events" in data
        assert len(data["events"]) > 0

    def test_get_nonexistent_task(self, web_env):
        resp = web_env.get("/api/tasks/nope")
        assert resp.status_code == 404


class TestWorktreesAPI:
    def test_list_worktrees(self, web_env):
        resp = web_env.get("/api/worktrees")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

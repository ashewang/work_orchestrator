"""Tests for task management operations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.core import projects as projects_mod
from work_orchestrator.db.engine import init_db


@pytest.fixture
def db():
    """Create a temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = init_db(db_path)
        projects_mod.create_project(conn, "test", "Test Project", tmp)
        yield conn
        conn.close()


class TestSlugify:
    def test_basic(self):
        assert tasks_mod.slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert tasks_mod.slugify("Auth: Login & Signup!") == "auth-login-signup"

    def test_multiple_spaces(self):
        assert tasks_mod.slugify("  too   many   spaces  ") == "too-many-spaces"

    def test_truncation(self):
        long_title = "a" * 100
        assert len(tasks_mod.slugify(long_title)) <= 60


class TestTaskCRUD:
    def test_create_task(self, db):
        task = tasks_mod.create_task(db, "Build login page", "test")
        assert task.id == "build-login-page"
        assert task.title == "Build login page"
        assert task.status == "todo"
        assert task.project_id == "test"

    def test_create_duplicate_gets_suffix(self, db):
        t1 = tasks_mod.create_task(db, "Build login page", "test")
        t2 = tasks_mod.create_task(db, "Build login page", "test")
        assert t1.id == "build-login-page"
        assert t2.id == "build-login-page-2"

    def test_get_task(self, db):
        tasks_mod.create_task(db, "My task", "test")
        task = tasks_mod.get_task(db, "my-task")
        assert task is not None
        assert task.title == "My task"

    def test_get_nonexistent_task(self, db):
        assert tasks_mod.get_task(db, "nonexistent") is None

    def test_list_tasks(self, db):
        tasks_mod.create_task(db, "Task 1", "test")
        tasks_mod.create_task(db, "Task 2", "test")
        tasks = tasks_mod.list_tasks(db, "test")
        assert len(tasks) == 2

    def test_list_tasks_by_status(self, db):
        tasks_mod.create_task(db, "Task A", "test")
        tasks_mod.create_task(db, "Task B", "test")
        tasks_mod.update_task_status(db, "task-a", "in-progress")
        todos = tasks_mod.list_tasks(db, "test", status="todo")
        assert len(todos) == 1
        assert todos[0].id == "task-b"

    def test_delete_task(self, db):
        tasks_mod.create_task(db, "Temp task", "test")
        assert tasks_mod.delete_task(db, "temp-task") is True
        assert tasks_mod.get_task(db, "temp-task") is None

    def test_delete_nonexistent(self, db):
        assert tasks_mod.delete_task(db, "nope") is False


class TestTaskStatus:
    def test_update_status(self, db):
        tasks_mod.create_task(db, "Status test", "test")
        task = tasks_mod.update_task_status(db, "status-test", "in-progress")
        assert task.status == "in-progress"

    def test_done_sets_completed_at(self, db):
        tasks_mod.create_task(db, "Done test", "test")
        task = tasks_mod.update_task_status(db, "done-test", "done")
        assert task.completed_at is not None

    def test_events_logged(self, db):
        tasks_mod.create_task(db, "Event test", "test")
        tasks_mod.update_task_status(db, "event-test", "in-progress")
        events = tasks_mod.get_task_events(db, "event-test")
        assert len(events) == 2  # created + status_changed
        assert events[0].event_type == "created"
        assert events[1].event_type == "status_changed"


class TestDependencies:
    def test_create_with_deps(self, db):
        tasks_mod.create_task(db, "First", "test")
        tasks_mod.create_task(db, "Second", "test", depends_on=["first"])
        task = tasks_mod.get_task(db, "second")
        assert "first" in task.depends_on

    def test_ready_tasks(self, db):
        tasks_mod.create_task(db, "Base", "test")
        tasks_mod.create_task(db, "Dependent", "test", depends_on=["base"])
        tasks_mod.create_task(db, "Independent", "test")

        ready = tasks_mod.get_ready_tasks(db, "test")
        ids = [t.id for t in ready]
        assert "base" in ids
        assert "independent" in ids
        assert "dependent" not in ids

    def test_ready_after_dep_done(self, db):
        tasks_mod.create_task(db, "Prereq", "test")
        tasks_mod.create_task(db, "Followup", "test", depends_on=["prereq"])

        tasks_mod.update_task_status(db, "prereq", "done")
        ready = tasks_mod.get_ready_tasks(db, "test")
        ids = [t.id for t in ready]
        assert "followup" in ids


class TestBreakdown:
    def test_break_down_task(self, db):
        tasks_mod.create_task(db, "Big task", "test")
        subs = tasks_mod.break_down_task(db, "big-task", [
            {"title": "Sub 1"},
            {"title": "Sub 2", "description": "Second subtask"},
        ])
        assert len(subs) == 2
        parent = tasks_mod.get_task(db, "big-task")
        assert len(parent.subtasks) == 2

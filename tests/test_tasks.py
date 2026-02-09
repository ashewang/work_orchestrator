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


class TestPriority:
    def test_default_priority(self, db):
        task = tasks_mod.create_task(db, "Default prio", "test")
        assert task.priority == 3

    def test_create_with_priority(self, db):
        task = tasks_mod.create_task(db, "Urgent", "test", priority=0)
        assert task.priority == 0

    def test_priority_clamped(self, db):
        task = tasks_mod.create_task(db, "Too high", "test", priority=99)
        assert task.priority == 6
        task2 = tasks_mod.create_task(db, "Too low", "test", priority=-5)
        assert task2.priority == 0

    def test_update_priority(self, db):
        tasks_mod.create_task(db, "Reprio", "test")
        task = tasks_mod.update_task_priority(db, "reprio", 1)
        assert task.priority == 1

    def test_update_priority_logged(self, db):
        tasks_mod.create_task(db, "Prio event", "test")
        tasks_mod.update_task_priority(db, "prio-event", 0)
        events = tasks_mod.get_task_events(db, "prio-event")
        prio_events = [e for e in events if e.event_type == "priority_changed"]
        assert len(prio_events) == 1
        assert prio_events[0].old_value == "3"
        assert prio_events[0].new_value == "0"

    def test_list_sorted_by_priority(self, db):
        tasks_mod.create_task(db, "Low prio", "test", priority=5)
        tasks_mod.create_task(db, "High prio", "test", priority=0)
        tasks_mod.create_task(db, "Mid prio", "test", priority=3)
        tasks = tasks_mod.list_tasks(db, "test")
        priorities = [t.priority for t in tasks]
        assert priorities == [0, 3, 5]

    def test_ready_tasks_sorted_by_priority(self, db):
        tasks_mod.create_task(db, "Low ready", "test", priority=5)
        tasks_mod.create_task(db, "High ready", "test", priority=1)
        ready = tasks_mod.get_ready_tasks(db, "test")
        assert ready[0].priority <= ready[-1].priority


class TestAddRemoveDependency:
    def test_add_dependency(self, db):
        tasks_mod.create_task(db, "Task A", "test")
        tasks_mod.create_task(db, "Task B", "test")
        task = tasks_mod.add_dependency(db, "task-b", "task-a")
        assert "task-a" in task.depends_on

    def test_add_dependency_idempotent(self, db):
        tasks_mod.create_task(db, "Task X", "test")
        tasks_mod.create_task(db, "Task Y", "test")
        tasks_mod.add_dependency(db, "task-y", "task-x")
        task = tasks_mod.add_dependency(db, "task-y", "task-x")
        assert task.depends_on.count("task-x") == 1

    def test_add_dependency_nonexistent_dep(self, db):
        tasks_mod.create_task(db, "Solo", "test")
        with pytest.raises(ValueError, match="not found"):
            tasks_mod.add_dependency(db, "solo", "nonexistent")

    def test_remove_dependency(self, db):
        tasks_mod.create_task(db, "Dep A", "test")
        tasks_mod.create_task(db, "Dep B", "test", depends_on=["dep-a"])
        task = tasks_mod.remove_dependency(db, "dep-b", "dep-a")
        assert "dep-a" not in task.depends_on

    def test_add_dep_logged(self, db):
        tasks_mod.create_task(db, "Log A", "test")
        tasks_mod.create_task(db, "Log B", "test")
        tasks_mod.add_dependency(db, "log-b", "log-a")
        events = tasks_mod.get_task_events(db, "log-b")
        dep_events = [e for e in events if e.event_type == "dependency_added"]
        assert len(dep_events) == 1
        assert dep_events[0].new_value == "log-a"

    def test_remove_dep_logged(self, db):
        tasks_mod.create_task(db, "Rem A", "test")
        tasks_mod.create_task(db, "Rem B", "test", depends_on=["rem-a"])
        tasks_mod.remove_dependency(db, "rem-b", "rem-a")
        events = tasks_mod.get_task_events(db, "rem-b")
        dep_events = [e for e in events if e.event_type == "dependency_removed"]
        assert len(dep_events) == 1
        assert dep_events[0].old_value == "rem-a"


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

    def test_break_down_with_priority(self, db):
        tasks_mod.create_task(db, "Parent task", "test")
        subs = tasks_mod.break_down_task(db, "parent-task", [
            {"title": "Urgent sub", "priority": 0},
            {"title": "Normal sub"},
        ])
        assert subs[0].priority == 0
        assert subs[1].priority == 3

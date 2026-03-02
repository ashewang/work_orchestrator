"""Tests for the CCPM-style planning engine."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from work_orchestrator.core import planner
from work_orchestrator.core import projects as projects_mod
from work_orchestrator.core import tasks as tasks_mod
from work_orchestrator.db.engine import init_db


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = init_db(db_path)
        projects_mod.create_project(conn, "test", "Test Project", "/tmp/repo")
        yield conn
        conn.close()


class TestSessionCRUD:
    def test_create_session(self, db):
        session = planner.create_session(db, "My Plan", project_id="test")
        assert session.id.startswith("plan-")
        assert session.project_id == "test"
        assert session.title == "My Plan"
        assert session.phase == "brainstorm"

    def test_get_session(self, db):
        session = planner.create_session(db, "Plan", project_id="test")
        fetched = planner.get_session(db, session.id)
        assert fetched is not None
        assert fetched.id == session.id

    def test_get_session_not_found(self, db):
        result = planner.get_session(db, "nonexistent")
        assert result is None

    def test_list_sessions(self, db):
        planner.create_session(db, "Plan A", project_id="test")
        planner.create_session(db, "Plan B", project_id="test")
        sessions = planner.list_sessions(db, project_id="test")
        assert len(sessions) == 2

    def test_list_sessions_all(self, db):
        planner.create_session(db, "Plan", project_id="test")
        sessions = planner.list_sessions(db)
        assert len(sessions) >= 1

    def test_update_phase(self, db):
        session = planner.create_session(db, "Plan", project_id="test")
        updated = planner.update_session_phase(db, session.id, "prd")
        assert updated.phase == "prd"

    def test_set_prd_content(self, db):
        session = planner.create_session(db, "Plan", project_id="test")
        updated = planner.set_prd_content(db, session.id, "# PRD\n\nHello")
        assert updated.prd_content == "# PRD\n\nHello"


class TestMessageCRUD:
    def test_add_and_get_messages(self, db):
        session = planner.create_session(db, "Plan", project_id="test")
        planner.add_message(db, session.id, "user", "Hello")
        planner.add_message(db, session.id, "assistant", "Hi there!")

        messages = planner.get_messages(db, session.id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Hello"
        assert messages[1].role == "assistant"

    def test_messages_ordered(self, db):
        session = planner.create_session(db, "Plan", project_id="test")
        planner.add_message(db, session.id, "user", "First")
        planner.add_message(db, session.id, "assistant", "Second")
        planner.add_message(db, session.id, "user", "Third")

        messages = planner.get_messages(db, session.id)
        assert len(messages) == 3
        assert [m.content for m in messages] == ["First", "Second", "Third"]


class TestBrainstormSystemPrompt:
    def test_includes_project_info(self, db):
        system = planner._build_brainstorm_system(db, "test")
        assert "Test Project" in system

    def test_includes_existing_tasks(self, db):
        tasks_mod.create_task(db, "Existing task", "test")
        system = planner._build_brainstorm_system(db, "test")
        assert "Existing task" in system
        assert "existing-task" in system


class TestPlanMessage:
    @patch("work_orchestrator.core.planner.anthropic")
    def test_plan_message(self, mock_anthropic, db):
        session = planner.create_session(db, "Plan", project_id="test")

        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Great idea! Let me ask a few questions.")]
        mock_client.messages.create.return_value = mock_response

        response = planner.plan_message(db, session.id, "I want to add auth")
        assert "Great idea" in response

        # Check messages were stored
        messages = planner.get_messages(db, session.id)
        assert len(messages) == 2
        assert messages[0].content == "I want to add auth"
        assert messages[1].content == "Great idea! Let me ask a few questions."

    @patch("work_orchestrator.core.planner.anthropic")
    def test_plan_message_nonexistent_session(self, mock_anthropic, db):
        with pytest.raises(ValueError, match="Session not found"):
            planner.plan_message(db, "nonexistent", "hello")


class TestGeneratePRD:
    @patch("work_orchestrator.core.planner.anthropic")
    def test_generate_prd(self, mock_anthropic, db):
        session = planner.create_session(db, "Auth Plan", project_id="test")
        planner.add_message(db, session.id, "user", "Add JWT auth")
        planner.add_message(db, session.id, "assistant", "Good idea!")

        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="# PRD: Auth\n\n## Vision\nAdd JWT auth")]
        mock_client.messages.create.return_value = mock_response

        prd = planner.generate_prd(db, session.id)
        assert "PRD" in prd

        # Check phase was updated
        updated = planner.get_session(db, session.id)
        assert updated.phase == "prd"
        assert updated.prd_content is not None


class TestDecomposePRD:
    @patch("work_orchestrator.core.planner.anthropic")
    def test_decompose(self, mock_anthropic, db):
        session = planner.create_session(db, "Plan", project_id="test")
        planner.set_prd_content(db, session.id, "# PRD\nBuild auth system")

        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_response = MagicMock()
        tasks_json = [
            {"title": "Add JWT library", "description": "Install and configure", "priority": 1, "depends_on": []},
            {"title": "Create login endpoint", "description": "POST /auth/login", "priority": 1, "depends_on": ["add-jwt-library"]},
        ]
        mock_response.content = [MagicMock(text=f"```json\n{__import__('json').dumps(tasks_json)}\n```")]
        mock_client.messages.create.return_value = mock_response

        tasks = planner.decompose_prd(db, session.id)
        assert len(tasks) == 2
        assert tasks[0]["title"] == "Add JWT library"

        updated = planner.get_session(db, session.id)
        assert updated.phase == "decompose"

    @patch("work_orchestrator.core.planner.anthropic")
    def test_decompose_no_prd(self, mock_anthropic, db):
        session = planner.create_session(db, "Plan", project_id="test")
        with pytest.raises(ValueError, match="No PRD content"):
            planner.decompose_prd(db, session.id)


class TestApprovePlan:
    def test_approve_creates_tasks(self, db):
        session = planner.create_session(db, "Plan", project_id="test")
        tasks_data = [
            {"title": "Task A", "description": "Do A", "priority": 1, "depends_on": []},
            {"title": "Task B", "description": "Do B", "priority": 2, "depends_on": ["task-a"]},
        ]
        created = planner.approve_plan(db, session.id, tasks_data)
        assert len(created) == 2
        assert created[0].title == "Task A"
        assert created[0].priority == 1

        # Check dependencies
        task_b = tasks_mod.get_task(db, created[1].id)
        assert created[0].id in task_b.depends_on

        # Check session phase
        updated = planner.get_session(db, session.id)
        assert updated.phase == "approved"

    def test_approve_empty_tasks(self, db):
        session = planner.create_session(db, "Plan", project_id="test")
        created = planner.approve_plan(db, session.id, [])
        assert len(created) == 0

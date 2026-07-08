"""Acceptance tests for approval-gated KOSINE suggestion execution (Phase 19b).

Covers the required contract:
  1. writes blocked when KOSINE_ALLOW_WRITES=false (nothing applied, not completed)
  2. an approved suggestion applies when KOSINE_ALLOW_WRITES=true
  3. every applied suggestion creates an audit record
  4. a failed write marks the workflow failed (never completed)
  5. destructive / unsupported operations are rejected

Plus guards: non-suggestion workflows are refused, and dry-run performs no write.

Run with:
    pytest backend/tests/test_kosine_apply.py -v
"""
from __future__ import annotations

import pytest


@pytest.fixture
def kos_env(tmp_path, monkeypatch):
    """Isolate the workflow db, the KOSINE db, and the audit log per test."""
    from backend import config
    from backend.app.memory import kosine_client, kosine_audit
    import backend.app.services.workflow_engine as wfe

    # Fresh WorkflowEngine backed by a temp db.
    monkeypatch.setattr(wfe, "DB_PATH", tmp_path / "cmdctr.db")
    monkeypatch.setattr(wfe, "_instance", None)

    # KOSINE enabled, in-process, pointed at a temp db; writes OFF by default.
    monkeypatch.setattr(config, "KOSINE_ENABLED", True)
    monkeypatch.setattr(config, "KOSINE_BASE_URL", "")
    monkeypatch.setattr(config, "KOSINE_DB_PATH", str(tmp_path / "kosine.db"))
    monkeypatch.setattr(config, "KOSINE_ALLOW_WRITES", False)
    kosine_client.reset()

    # Audit log to a temp file.
    monkeypatch.setattr(kosine_audit, "_AUDIT_DIR", tmp_path)
    monkeypatch.setattr(kosine_audit, "_AUDIT_PATH", tmp_path / "kosine_audit.jsonl")

    yield {"config": config, "client_mod": kosine_client, "audit": kosine_audit, "tmp": tmp_path}

    kosine_client.reset()


def _engine():
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine()


def _make_suggestion(tool: str, args: dict, title: str = "test suggestion") -> str:
    """Create a draft KOSINE-suggestion workflow, return its code."""
    wf = _engine().create(
        category="kosine_suggestion",
        title=title,
        description="test",
        risk_level="low",
        tool_name=tool,
        tool_args=args,
        project="KOSINE",
        template="kosine_suggestion",
        auto_submit=False,
    )
    return wf["code"]


def _new_object(kos_env, obj_type="Observation", title="apply-target", **fields) -> str:
    """Create a KOSINE object directly (test setup, not via the gated path)."""
    client = kos_env["client_mod"].get_client()
    return client.create_memory(type=obj_type, title=title, **fields)["id"]


# ── 1. writes blocked when allow_writes=false ─────────────────────────────────

def test_writes_blocked_when_allow_writes_false(kos_env):
    from backend.app.services import kosine_apply

    oid = _new_object(kos_env, description="original")
    code = _make_suggestion("update_memory", {"target": oid, "description": "changed"})

    res = kosine_apply.apply_suggestion(code, approve=True)

    assert res["ok"] is False
    assert "KOSINE_ALLOW_WRITES" in res["error"] or "disabled" in res["error"].lower()
    # Approved but NOT completed — can be applied later once writes are enabled.
    wf = _engine().get(code)
    assert wf["status"] == "approved"
    assert wf["status"] != "completed"
    # Object untouched.
    obj = kos_env["client_mod"].get_client().show_object(oid)["object"]
    assert obj["description"] == "original"
    # No audit record was written.
    assert kos_env["audit"].read_audit() == []


# ── 2. approved suggestion applies when allow_writes=true ─────────────────────

def test_approved_suggestion_applies_when_allow_writes_true(kos_env, monkeypatch):
    from backend import config
    from backend.app.services import kosine_apply

    oid = _new_object(kos_env, description="original")
    code = _make_suggestion("update_memory", {"target": oid, "description": "applied-value"})

    monkeypatch.setattr(config, "KOSINE_ALLOW_WRITES", True)
    res = kosine_apply.apply_suggestion(code, approve=True)

    assert res["ok"] is True
    assert res["status"] == "completed"
    wf = _engine().get(code)
    assert wf["status"] == "completed"
    # The write actually landed.
    obj = kos_env["client_mod"].get_client().show_object(oid)["object"]
    assert obj["description"] == "applied-value"


# ── 3. audit record created ───────────────────────────────────────────────────

def test_apply_creates_audit_record(kos_env, monkeypatch):
    from backend import config
    from backend.app.services import kosine_apply

    oid = _new_object(kos_env, description="original")
    code = _make_suggestion("update_memory", {"target": oid, "description": "v2"})

    monkeypatch.setattr(config, "KOSINE_ALLOW_WRITES", True)
    kosine_apply.apply_suggestion(code, approve=True)

    records = kos_env["audit"].read_audit()
    assert len(records) >= 1
    rec = records[0]
    assert rec["tool"] == "update_memory"
    assert rec["status"] == "ok"
    assert oid in rec["objects_changed"]
    assert rec["reason"] == f"apply {code}"


# ── 4. failed write marks workflow failed ─────────────────────────────────────

def test_failed_write_marks_workflow_failed(kos_env, monkeypatch):
    from backend import config
    from backend.app.memory import kosine_audit
    from backend.app.services import kosine_apply

    oid = _new_object(kos_env, description="original")
    code = _make_suggestion("update_memory", {"target": oid, "description": "v3"})

    monkeypatch.setattr(config, "KOSINE_ALLOW_WRITES", True)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated KOSINE write failure")

    monkeypatch.setattr(kosine_audit, "audited_write", _boom)

    res = kosine_apply.apply_suggestion(code, approve=True)

    assert res["ok"] is False
    assert "simulated KOSINE write failure" in res["error"]
    wf = _engine().get(code)
    assert wf["status"] == "failed"
    assert wf["status"] != "completed"


# ── 5. destructive / unsupported operation rejected ───────────────────────────

def test_destructive_operation_rejected(kos_env, monkeypatch):
    from backend import config
    from backend.app.memory import kosine_audit
    from backend.app.services import kosine_apply

    # allow_writes ON so the ONLY thing stopping execution is the destructive guard.
    monkeypatch.setattr(config, "KOSINE_ALLOW_WRITES", True)

    called = {"n": 0}

    def _spy(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("audited_write must not run for a destructive op")

    monkeypatch.setattr(kosine_audit, "audited_write", _spy)

    code = _make_suggestion("delete_object", {"target": "whatever"}, title="destructive")
    res = kosine_apply.apply_suggestion(code, approve=True)

    assert res["ok"] is False
    assert "not permitted" in res["error"].lower() or "destructive" in res["error"].lower()
    assert called["n"] == 0                      # never reached execution
    wf = _engine().get(code)
    assert wf["status"] == "failed"
    assert wf["status"] != "completed"


# ── guards ────────────────────────────────────────────────────────────────────

def test_non_suggestion_workflow_refused(kos_env, monkeypatch):
    from backend import config
    from backend.app.services import kosine_apply

    monkeypatch.setattr(config, "KOSINE_ALLOW_WRITES", True)
    wf = _engine().create(
        category="memory_update", title="not a kosine suggestion",
        tool_name="update_memory", tool_args={"target": "x"}, auto_submit=False,
    )
    res = kosine_apply.apply_suggestion(wf["code"], approve=True)
    assert res["ok"] is False
    assert "not a KOSINE suggestion" in res["error"]


def test_dry_run_performs_no_write(kos_env, monkeypatch):
    from backend import config
    from backend.app.services import kosine_apply

    oid = _new_object(kos_env, description="original")
    code = _make_suggestion("update_memory", {"target": oid, "description": "nope"})

    monkeypatch.setattr(config, "KOSINE_ALLOW_WRITES", True)
    res = kosine_apply.apply_suggestion(code, approve=True, dry_run=True)

    assert res["ok"] is True
    assert res["dry_run"] is True
    assert res["would_apply"]["tool"] == "update_memory"
    # Status stays approved (dry-run changes nothing) and object is untouched.
    assert _engine().get(code)["status"] == "approved"
    obj = kos_env["client_mod"].get_client().show_object(oid)["object"]
    assert obj["description"] == "original"
    assert kos_env["audit"].read_audit() == []

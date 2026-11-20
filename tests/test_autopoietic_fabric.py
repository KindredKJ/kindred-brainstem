"""KACF v0.1 durable branching, verified collapse, utility and HCM tests."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from contextlib import contextmanager

import pytest
from brainstem.fabric.autopoietic import AutopoieticFabric, FabricConflict


class _Store:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE workforce_tasks (
                    task_id TEXT PRIMARY KEY, required_capability TEXT,
                    status TEXT, last_error TEXT
                );
                CREATE TABLE task_receipts (
                    task_id TEXT PRIMARY KEY, receipt_json TEXT,
                    output_sha256 TEXT, verified_at TEXT
                );
                CREATE TABLE workforce_observations (
                    source TEXT,worker_id TEXT,reported_status TEXT,observed_at TEXT
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


@pytest.fixture
def fabric(tmp_path):
    store = _Store(tmp_path / "fabric.db")
    return store, AutopoieticFabric(store)


def create(store, task_id, status="queued", capability="runtime.snapshot"):
    with store.connect() as db:
        db.execute("INSERT INTO workforce_tasks VALUES (?,?,?,NULL)",
                   (task_id, capability, status))


def verify(store, task_id, ns=100_000_000):
    receipt = {"task_id": task_id, "status": "completed",
               "causal_proof": {"elapsed_ns": ns}, "signature": "verified_upstream"}
    with store.connect() as db:
        db.execute("UPDATE workforce_tasks SET status='verified_complete' WHERE task_id=?", (task_id,))
        db.execute("INSERT INTO task_receipts VALUES (?,?,?,?)",
                   (task_id, json.dumps(receipt), hashlib.sha256(b"output").hexdigest(),
                    "2026-11-20T00:00:00+00:00"))


def test_prepare_is_inert_and_receipt_required(fabric):
    store, engine = fabric
    create(store, "task_1")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        prepared = engine.prepare_in_transaction(
            db, task_id="task_1", capability="runtime.snapshot", payload_sha256="a" * 64
        )
        assert prepared["dispatch_policy"] == "single"
        assert prepared["branches"]["succeeded"]["side_effects"] is False
        with pytest.raises(FabricConflict, match="no durable verified"):
            engine.collapse_verified_in_transaction(db, task_id="task_1")
    assert engine.summary()["forks"][0]["status"] == "prepared"


def test_verified_collapse_idempotence_and_measured_proxy(fabric):
    store, engine = fabric
    create(store, "task_2")
    with store.connect() as db:
        engine.prepare_in_transaction(db, task_id="task_2", capability="runtime.snapshot", payload_sha256="b" * 64)
    verify(store, "task_2")
    with store.connect() as db:
        first = engine.collapse_verified_in_transaction(db, task_id="task_2")
    with store.connect() as db:
        second = engine.collapse_verified_in_transaction(db, task_id="task_2")
    assert first["outcome"] == "succeeded" and first["measured_latency_ns"] == 100_000_000
    assert second["replayed"] is True
    metric = engine.summary()["metabolics"][0]
    assert metric["samples"] == 1 and metric["utility_per_measured_second"] == 10
    assert metric["joules"] is None


def test_policy_switches_after_measured_samples(fabric):
    store, engine = fabric
    for i in range(1, 5):
        task_id = f"task_{i}"
        create(store, task_id)
        with store.connect() as db:
            result = engine.prepare_in_transaction(
                db, task_id=task_id, capability="runtime.snapshot", payload_sha256="c" * 64
            )
        if i < 4:
            assert result["dispatch_policy"] == "single"
            verify(store, task_id)
            with store.connect() as db:
                engine.collapse_verified_in_transaction(db, task_id=task_id)
        else:
            assert result["dispatch_policy"] == "speculative"


def test_prepared_evidence_tampering_aborts_collapse(fabric):
    store, engine = fabric
    create(store, "task_broken")
    with store.connect() as db:
        engine.prepare_in_transaction(db, task_id="task_broken", capability="runtime.snapshot", payload_sha256="d" * 64)
    verify(store, "task_broken")
    with store.connect() as db:
        db.execute("UPDATE kacf_forks SET branch_json='{}' WHERE task_id='task_broken'")
    with pytest.raises(FabricConflict, match="modified"):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            engine.collapse_verified_in_transaction(db, task_id="task_broken")
    assert engine.summary()["forks"][0]["status"] == "prepared"


def test_hcm_incident_reconciliation_is_idempotent(fabric):
    store, engine = fabric
    create(store, "task_fail", status="dead_letter", capability="signal.deliver")
    assert engine.reconcile_terminal_incidents() == 1
    assert engine.reconcile_terminal_incidents() == 0
    state = engine.summary()
    assert state["hcm_recovery_queue"][0]["capability"] == "signal.deliver"
    assert state["hcm_scope"] == "recovery_proposals_no_worker_synthesis"

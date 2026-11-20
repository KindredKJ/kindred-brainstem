"""KACF v0.1: bounded cognitive forks and evidence-derived cost feedback.

Data speculation only: no extra model inference, worker synthesis, joule
measurement, monetary return, or speculative side effects.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

MAX_BRANCH_BYTES = 8192


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class FabricConflict(ValueError):
    pass


class AutopoieticFabric:
    """Task-indexed SQLite state machine; receipt + fork collapse share one txn."""

    def __init__(self, store: Any, *, speculation_min_samples: int = 3,
                 speculation_min_utility_per_second: float = 1.0) -> None:
        self.store = store
        self.min_samples = max(1, int(speculation_min_samples))
        self.min_utility_per_second = float(speculation_min_utility_per_second)
        if not math.isfinite(self.min_utility_per_second) or self.min_utility_per_second < 0:
            raise ValueError("invalid speculation threshold")
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS kacf_forks (
                    task_id TEXT PRIMARY KEY,
                    capability TEXT NOT NULL,
                    state_digest TEXT NOT NULL,
                    branch_sha256 TEXT NOT NULL,
                    branch_json TEXT NOT NULL,
                    dispatch_policy TEXT NOT NULL CHECK(dispatch_policy IN ('single','speculative')),
                    status TEXT NOT NULL CHECK(status IN ('prepared','collapsed')),
                    outcome TEXT,
                    receipt_hash TEXT,
                    created_at TEXT NOT NULL,
                    collapsed_at TEXT,
                    FOREIGN KEY(task_id) REFERENCES workforce_tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS kacf_metabolics (
                    capability TEXT PRIMARY KEY,
                    samples INTEGER NOT NULL DEFAULT 0,
                    verified_successes INTEGER NOT NULL DEFAULT 0,
                    recorded_failures INTEGER NOT NULL DEFAULT 0,
                    measured_latency_ns INTEGER NOT NULL DEFAULT 0,
                    utility_proxy_units INTEGER NOT NULL DEFAULT 0,
                    energy_measurement_status TEXT NOT NULL DEFAULT 'unavailable',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kacf_capability_incidents (
                    incident_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL UNIQUE,
                    capability TEXT NOT NULL,
                    cause TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued','reviewed')),
                    evidence_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    @staticmethod
    def _state_digest(db: Any, payload_sha256: str) -> str:
        observed = [list(r) for r in db.execute(
            "SELECT source,worker_id,reported_status,observed_at "
            "FROM workforce_observations ORDER BY source,worker_id LIMIT 256"
        )]
        last = db.execute(
            "SELECT task_id,output_sha256 FROM task_receipts "
            "ORDER BY verified_at DESC,task_id DESC LIMIT 1"
        ).fetchone()
        return digest({"payload_sha256": payload_sha256, "observed_workers": observed,
                       "last_verified": list(last) if last is not None else None})

    @staticmethod
    def _metric(db: Any, capability: str) -> dict[str, Any]:
        row = db.execute("SELECT * FROM kacf_metabolics WHERE capability=?", (capability,)).fetchone()
        if row is None:
            return {"capability": capability, "samples": 0, "verified_successes": 0,
                    "recorded_failures": 0, "measured_latency_ns": 0,
                    "utility_proxy_units": 0, "energy_measurement_status": "unavailable",
                    "utility_per_measured_second": None, "joules": None}
        result = dict(row)
        duration = result["measured_latency_ns"]
        result["utility_per_measured_second"] = (
            round(result["utility_proxy_units"] * 1_000_000_000 / duration, 6)
            if duration > 0 else None
        )
        result["joules"] = None
        return result

    def prepare_in_transaction(self, db: Any, *, task_id: str, capability: str,
                               payload_sha256: str) -> dict[str, Any]:
        """Materialize bounded inert candidate deltas."""
        current = db.execute("SELECT * FROM kacf_forks WHERE task_id=?", (task_id,)).fetchone()
        if current is not None:
            if current["capability"] != capability:
                raise FabricConflict("task already prepared under a different capability")
            return dict(current)
        met = self._metric(db, capability)
        policy = ("speculative" if met["samples"] >= self.min_samples and
                  met["utility_per_measured_second"] is not None and
                  met["utility_per_measured_second"] >= self.min_utility_per_second
                  else "single")
        deltas = {
            "succeeded": {"task_status": "verified_complete", "side_effects": False},
            "failed": {"task_status": "failed", "side_effects": False},
            "timed_out": {"task_status": "expired", "side_effects": False},
        }
        packed = canonical(deltas)
        if len(packed) > MAX_BRANCH_BYTES:
            raise ValueError("branch cap exceeded")
        snapshot = self._state_digest(db, payload_sha256)
        db.execute("""INSERT INTO kacf_forks
            (task_id,capability,state_digest,branch_sha256,branch_json,dispatch_policy,
             status,outcome,receipt_hash,created_at,collapsed_at)
             VALUES (?,?,?,?,?,?,'prepared',NULL,NULL,?,NULL)""",
            (task_id, capability, snapshot, hashlib.sha256(packed).hexdigest(),
             packed.decode("utf-8"), policy, utcnow()),
        )
        return {"task_id": task_id, "capability": capability, "state_digest": snapshot,
                "dispatch_policy": policy, "status": "prepared", "branches": deltas}

    def collapse_verified_in_transaction(self, db: Any, *, task_id: str) -> dict[str, Any]:
        """Collapse only when already-verified receipt + task completion are durable."""
        fork = db.execute("SELECT * FROM kacf_forks WHERE task_id=?", (task_id,)).fetchone()
        if fork is None:
            raise FabricConflict("task lacks a prepared fork")
        row = db.execute("""SELECT t.status,t.required_capability,r.receipt_json
            FROM workforce_tasks t JOIN task_receipts r ON r.task_id=t.task_id
            WHERE t.task_id=?""", (task_id,)).fetchone()
        if row is None or row["status"] != "verified_complete":
            raise FabricConflict("no durable verified task receipt")
        receipt = json.loads(row["receipt_json"])
        if receipt.get("task_id") != task_id or receipt.get("status") != "completed":
            raise FabricConflict("receipt does not support success collapse")
        receipt_hash = digest(receipt)
        if fork["status"] == "collapsed":
            if fork["receipt_hash"] == receipt_hash and fork["outcome"] == "succeeded":
                return {"task_id": task_id, "outcome": "succeeded", "replayed": True}
            raise FabricConflict("task already collapsed under different evidence")
        branches = json.loads(fork["branch_json"])
        if hashlib.sha256(canonical(branches)).hexdigest() != fork["branch_sha256"]:
            raise FabricConflict("prepared branch evidence was modified")
        proof = receipt.get("causal_proof")
        elapsed = proof.get("elapsed_ns") if isinstance(proof, dict) else None
        if type(elapsed) is not int or elapsed < 0:
            elapsed = None
        result = db.execute("""UPDATE kacf_forks
            SET status='collapsed',outcome='succeeded',receipt_hash=?,collapsed_at=?
            WHERE task_id=? AND status='prepared'""", (receipt_hash, utcnow(), task_id))
        if result.rowcount != 1:
            raise FabricConflict("fork collapse lost transaction race")
        if elapsed is not None:
            db.execute("""INSERT INTO kacf_metabolics
                (capability,samples,verified_successes,recorded_failures,
                 measured_latency_ns,utility_proxy_units,energy_measurement_status,updated_at)
                VALUES (?,1,1,0,?,1,'unavailable',?)
                ON CONFLICT(capability) DO UPDATE SET
                  samples=samples+1,verified_successes=verified_successes+1,
                  measured_latency_ns=measured_latency_ns+excluded.measured_latency_ns,
                  utility_proxy_units=utility_proxy_units+1,
                  updated_at=excluded.updated_at""",
                (row["required_capability"], elapsed, utcnow()),
            )
        return {"task_id": task_id, "outcome": "succeeded", "replayed": False,
                "branch_delta": branches["succeeded"], "measured_latency_ns": elapsed,
                "receipt_hash": receipt_hash}

    def reconcile_terminal_incidents(self) -> int:
        """Queue HCM proposals from genuine dead letters; never invent worker status."""
        inserted = 0
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute("""SELECT task_id,required_capability,status,last_error
                 FROM workforce_tasks WHERE status IN ('dead_letter','expired')""").fetchall():
                marker = digest({"task_id": row["task_id"], "status": row["status"],
                                 "last_error": row["last_error"]})
                result = db.execute("""INSERT OR IGNORE INTO kacf_capability_incidents
                    (incident_id,task_id,capability,cause,status,evidence_digest,created_at)
                    VALUES (?,?,?,?,'queued',?,?)""",
                    ("hcm_" + marker[:32], row["task_id"], row["required_capability"],
                     row["status"], marker, utcnow()),
                )
                inserted += result.rowcount
        return inserted

    def summary(self, limit: int = 10) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        with self.store.connect() as db:
            forks = [dict(r) for r in db.execute(
                "SELECT task_id,capability,state_digest,dispatch_policy,status,outcome,created_at "
                "FROM kacf_forks ORDER BY created_at DESC LIMIT ?", (limit,)
            )]
            metrics = [self._metric(db, r["capability"]) for r in db.execute(
                "SELECT capability FROM kacf_metabolics ORDER BY capability LIMIT ?", (limit,)
            )]
            incidents = [dict(r) for r in db.execute(
                "SELECT * FROM kacf_capability_incidents ORDER BY created_at DESC LIMIT ?", (limit,)
            )]
        return {"schema": "kindred.kacf.state.v0.1", "forks": forks,
                "metabolics": metrics, "hcm_recovery_queue": incidents,
                "energy_source": "unmeasured", "monetary_value": "not_calibrated",
                "esccb_scope": "inert_state_deltas_only",
                "hcm_scope": "recovery_proposals_no_worker_synthesis"}

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.execution_worker import run_once
from app.main import app
from app.production_control import (
    ProductionControlStore,
    canonical_release_hash,
    reset_production_store_for_tests,
)


def release_manifest(artifact_hash: str = "a" * 64) -> dict[str, object]:
    manifest: dict[str, object] = {
        "run_id": "front-production-test",
        "approved_artifacts": ["mrs_transform.py"],
        "artifact_hashes": {"mrs_transform.py": artifact_hash},
        "files": [
            {
                "name": "approval_summary.json",
                "sha256": "b" * 64,
            }
        ],
    }
    manifest["release_hash"] = canonical_release_hash(manifest)
    return manifest


class ProductionControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "control.db"
        self.target_patcher = patch.dict(
            os.environ,
            {"SAT_ALLOWED_EXECUTION_TARGETS": "dry_run"},
            clear=False,
        )
        self.target_patcher.start()
        self.store = ProductionControlStore(f"sqlite:///{self.db_path.as_posix()}")

    def approve_manifest_artifacts(
        self,
        store: ProductionControlStore,
        manifest: dict[str, object],
    ) -> None:
        for artifact_name, artifact_hash in manifest["artifact_hashes"].items():
            store.record_artifact_approval(
                run_id=str(manifest["run_id"]),
                artifact_name=str(artifact_name),
                artifact_hash=str(artifact_hash),
                decision="approved",
                actor="artifact-reviewer@example.com",
                note="approved for production-control test",
            )

    def tearDown(self) -> None:
        self.store.engine.dispose()
        reset_production_store_for_tests()
        self.target_patcher.stop()
        self.temp_dir.cleanup()

    def test_release_hash_changes_when_artifact_changes(self) -> None:
        first = canonical_release_hash(release_manifest("a" * 64))
        second = canonical_release_hash(release_manifest("c" * 64))
        self.assertNotEqual(first, second)

    def test_four_eyes_and_worker_state_machine(self) -> None:
        manifest = release_manifest()
        self.approve_manifest_artifacts(self.store, manifest)
        release = self.store.record_release(
            run_id="front-production-test",
            manifest=manifest,
            actor="release-manager@example.com",
        )
        request = self.store.create_execution_request(
            run_id="front-production-test",
            release_hash=release["release_hash"],
            target="dry_run",
            parameters={"reason": "controlled validation"},
            idempotency_key="production-test-001",
            actor="release-manager@example.com",
        )
        with self.assertRaisesRegex(ValueError, "Four-eyes"):
            self.store.approve_execution(
                request["request_id"],
                "release-manager@example.com",
                "self approval must fail",
            )

        approved = self.store.approve_execution(
            request["request_id"],
            "cloud-operator@example.com",
            "approved test window",
        )
        self.assertEqual(approved["status"], "queued")
        claimed = self.store.claim_next_execution("worker:test")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["status"], "running")
        completed = self.store.update_execution(
            request["request_id"],
            status="succeeded",
            actor="worker:test",
            cloud_job_id="dry-run-test",
            evidence={"write_calls": 0},
        )
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed["evidence"]["write_calls"], 0)

    def test_idempotency_key_reuses_identical_request_and_rejects_conflict(self) -> None:
        manifest = release_manifest()
        self.approve_manifest_artifacts(self.store, manifest)
        release = self.store.record_release(
            run_id="front-production-test",
            manifest=manifest,
            actor="release-manager@example.com",
        )
        first = self.store.create_execution_request(
            run_id="front-production-test",
            release_hash=release["release_hash"],
            target="dry_run",
            parameters={"year": 2025},
            idempotency_key="production-test-002",
            actor="release-manager@example.com",
        )
        second = self.store.create_execution_request(
            run_id="front-production-test",
            release_hash=release["release_hash"],
            target="dry_run",
            parameters={"year": 2025},
            idempotency_key="production-test-002",
            actor="release-manager@example.com",
        )
        self.assertEqual(first["request_id"], second["request_id"])
        with self.assertRaisesRegex(ValueError, "different execution request"):
            self.store.create_execution_request(
                run_id="front-production-test",
                release_hash=release["release_hash"],
                target="dry_run",
                parameters={"year": 2026},
                idempotency_key="production-test-002",
                actor="release-manager@example.com",
            )

    def test_secret_like_execution_parameter_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Secret-like"):
            self.store.create_execution_request(
                run_id="front-production-test",
                release_hash="a" * 64,
                target="dry_run",
                parameters={"access_key": "must-not-be-stored"},
                idempotency_key="production-test-003",
                actor="release-manager@example.com",
            )

    def test_release_rejects_missing_or_stale_persisted_approval(self) -> None:
        manifest = release_manifest()
        with self.assertRaisesRegex(ValueError, "persisted approvals"):
            self.store.record_release(
                run_id="front-production-test",
                manifest=manifest,
                actor="release-manager@example.com",
            )
        self.store.record_artifact_approval(
            run_id="front-production-test",
            artifact_name="mrs_transform.py",
            artifact_hash="c" * 64,
            decision="approved",
            actor="artifact-reviewer@example.com",
            note="approved a different artifact version",
        )
        with self.assertRaisesRegex(ValueError, "persisted approvals"):
            self.store.record_release(
                run_id="front-production-test",
                manifest=manifest,
                actor="release-manager@example.com",
            )

    def test_production_auth_fails_closed_and_accepts_trusted_identity(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SAT_PRODUCTION_MODE": "true",
                "SAT_AUTH_MODE": "trusted_header",
            },
            clear=False,
        ):
            anonymous = TestClient(app).get("/api/auth/me")
            self.assertEqual(anonymous.status_code, 401)
            authenticated = TestClient(app).get(
                "/api/auth/me",
                headers={
                    "X-SAT-User": "reviewer@example.com",
                    "X-SAT-Roles": "artifact_reviewer,auditor",
                },
            )
            self.assertEqual(authenticated.status_code, 200)
            payload = authenticated.json()
            self.assertTrue(payload["authenticated"])
            self.assertTrue(payload["permissions"]["review_artifact"])
            self.assertFalse(payload["permissions"]["release"])

    def test_dry_run_worker_records_terminal_evidence_without_cloud_writes(self) -> None:
        db_url = f"sqlite:///{self.db_path.as_posix()}"
        with patch.dict(
            os.environ,
            {
                "SAT_DATABASE_URL": db_url,
                "SAT_PRODUCTION_MODE": "true",
                "SAT_CLOUD_EXECUTION_ENABLED": "true",
                "SAT_ALLOWED_EXECUTION_TARGETS": "dry_run",
                "SAT_EXECUTION_POLL_SECONDS": "2",
            },
            clear=False,
        ):
            reset_production_store_for_tests()
            store = ProductionControlStore(db_url)
            manifest = release_manifest()
            self.approve_manifest_artifacts(store, manifest)
            release = store.record_release(
                run_id="front-production-test",
                manifest=manifest,
                actor="release-manager@example.com",
            )
            request = store.create_execution_request(
                run_id="front-production-test",
                release_hash=release["release_hash"],
                target="dry_run",
                parameters={"reason": "worker integration test"},
                idempotency_key="production-test-004",
                actor="release-manager@example.com",
            )
            store.approve_execution(
                request["request_id"],
                "cloud-operator@example.com",
                "approved",
            )
            store.engine.dispose()

            result = run_once("worker:integration-test")
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["evidence"]["submission"]["write_calls"], 0)
            self.assertEqual(result["evidence"]["terminal"]["write_calls"], 0)

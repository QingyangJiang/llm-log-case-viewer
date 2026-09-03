import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")

import backend.app.main as api


class JudgeHelpersTest(unittest.TestCase):
    def test_case_and_candidate_hashes_invalidate_only_the_changed_scope(self) -> None:
        original = {
            "id": "case-1",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [],
            "candidates": [
                {"id": "a", "model": "model-a", "response": "old"},
                {"id": "b", "model": "model-b", "response": "same"},
            ],
            "annotation_config": {"dimensions": []},
        }
        updated = {
            **original,
            "candidates": [
                {"id": "a", "model": "model-a", "response": "new"},
                {"id": "b", "model": "model-b", "response": "same"},
            ],
        }

        self.assertEqual(
            api.canonical_hash(api.judge_case_content(original)),
            api.canonical_hash(api.judge_case_content(updated)),
        )
        self.assertNotEqual(
            api.canonical_hash(api.judge_candidate_content(original["candidates"][0])),
            api.canonical_hash(api.judge_candidate_content(updated["candidates"][0])),
        )
        self.assertEqual(
            api.canonical_hash(api.judge_candidate_content(original["candidates"][1])),
            api.canonical_hash(api.judge_candidate_content(updated["candidates"][1])),
        )

    def test_stage3_uses_median_score_and_majority_tier(self) -> None:
        result = api.aggregate_stage3([
            {"tier": 1, "score": 8, "overall_comment": "a"},
            {"tier": 2, "score": 7, "overall_comment": "b"},
            {"tier": 1, "score": 9, "overall_comment": "c"},
        ])

        self.assertEqual(result["consensus"]["score"], 8)
        self.assertEqual(result["consensus"]["tier"], 1)
        self.assertEqual(result["consensus"]["score_range"], [7, 9])
        self.assertFalse(result["consensus"]["stable"])

    def test_json_parser_keeps_unparseable_output_for_review(self) -> None:
        parsed = api.parse_json_object("not json")
        self.assertEqual(parsed["raw_output"], "not json")
        self.assertIn("parse_error", parsed)

    def test_errors_redact_api_keys(self) -> None:
        message = api.redact_judge_error("request failed with secret-token", "secret-token")
        self.assertNotIn("secret-token", message)
        self.assertIn("***", message)

    def test_worker_runs_three_stages_once_and_persists_results(self) -> None:
        test_engine = api.create_engine("sqlite://", connect_args={"check_same_thread": False})
        test_session = api.sessionmaker(test_engine, expire_on_commit=False)
        api.Base.metadata.create_all(test_engine)
        config = {**api.default_judge_config(), "sample_count": 1}
        with test_session() as db:
            user = api.User(username="judge-admin", display_name="Judge Admin", password_hash="unused", role="admin")
            db.add(user)
            db.flush()
            project = api.Project(name="Judge Project", annotation_config={}, created_by=user.id)
            db.add(project)
            db.flush()
            payload = {
                "id": "case-1",
                "messages": [{"role": "user", "content": "answer this"}],
                "candidates": [{"id": "candidate-1", "model": "demo", "response": "answer"}],
            }
            case = api.Case(project_id=project.id, external_id="case-1", ordinal=0, payload=payload)
            db.add(case)
            db.flush()
            config_record = api.JudgeConfigVersion(
                project_id=project.id,
                version=1,
                config=config,
                api_key="server-secret",
                signature=api.judge_config_signature(config),
                active=True,
                created_by=user.id,
            )
            db.add(config_record)
            db.flush()
            case_run = api.JudgeCaseRun(
                project_id=project.id,
                case_id=case.id,
                config_id=config_record.id,
                case_hash=api.canonical_hash(api.judge_case_content(payload)),
                status="queued",
                triggered_by=user.id,
            )
            db.add(case_run)
            db.flush()
            candidate = payload["candidates"][0]
            db.add(api.JudgeCandidateRun(
                case_run_id=case_run.id,
                candidate_id="candidate-1",
                candidate_hash=api.canonical_hash(api.judge_candidate_content(candidate)),
                status="queued",
            ))
            db.commit()
            case_run_id = case_run.id

        responses = iter([
            '{"full_goal":"目标","current_stage":"开始","subtasks":[{"id":1,"desc":"回答","phase":"pending"}]}',
            '{"subtasks":[{"id":1,"status":"done","findings":[],"correct_points":"正确"}]}',
            '{"tier":1,"score":9,"score_rationale":"完成良好"}',
        ])
        original_session = api.SessionLocal
        api.SessionLocal = test_session
        try:
            with patch.object(api, "call_judge_model", side_effect=lambda *args, **kwargs: next(responses)) as model_call:
                api._judge_case_worker(case_run_id)
                api._judge_case_worker(case_run_id)
                self.assertEqual(model_call.call_count, 3)
        finally:
            api.SessionLocal = original_session
            api._judge_config_semaphores.clear()

        with test_session() as db:
            saved_case = db.get(api.JudgeCaseRun, case_run_id)
            saved_candidate = db.scalar(api.select(api.JudgeCandidateRun).where(api.JudgeCandidateRun.case_run_id == case_run_id))
            self.assertEqual(saved_case.status, "succeeded")
            self.assertEqual(saved_candidate.status, "succeeded")
            self.assertEqual(saved_candidate.stage3_result["consensus"]["score"], 9)


if __name__ == "__main__":
    unittest.main()

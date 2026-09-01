import math
import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")

from backend.app.main import Annotation, Case, Project, User, project_metrics_payload


def annotation(user: User, candidate_id: str, score: int, badcase: bool = False) -> Annotation:
    return Annotation(
        candidate_id=candidate_id,
        user_id=user.id,
        user=user,
        scores={"quality": score},
        badcase=badcase,
        badcase_tags=[],
        note="",
        status="submitted",
        revision=1,
    )


class MetricsPayloadTest(unittest.TestCase):
    def test_complete_cases_are_case_weighted_and_incomplete_cases_are_dropped(self) -> None:
        alice = User(id=1, username="alice", display_name="Alice", password_hash="x", role="annotator")
        bob = User(id=2, username="bob", display_name="Bob", password_hash="x", role="annotator")
        project = Project(
            id=1,
            name="Metrics",
            created_by=1,
            annotation_config={
                "dimensions": [{"key": "quality", "label": "质量", "min": 1, "max": 10}],
                "model_order": ["model-b", "model-a"],
            },
        )
        complete_one = Case(
            id=1,
            project_id=1,
            external_id="case-1",
            ordinal=0,
            payload={"candidates": [{"id": "a-1", "model": "model-a"}, {"id": "b-1", "model": "model-b"}]},
            annotations=[
                annotation(alice, "a-1", 8, True),
                annotation(bob, "a-1", 10, False),
                annotation(alice, "b-1", 4),
                annotation(bob, "b-1", 8),
            ],
        )
        complete_two = Case(
            id=2,
            project_id=1,
            external_id="case-2",
            ordinal=1,
            payload={"candidates": [{"id": "a-2", "model": "model-a"}, {"id": "b-2", "model": "model-b"}]},
            annotations=[annotation(alice, "a-2", 7), annotation(alice, "b-2", 2, True)],
        )
        incomplete = Case(
            id=3,
            project_id=1,
            external_id="case-3",
            ordinal=2,
            payload={"candidates": [{"id": "a-3", "model": "model-a"}, {"id": "b-3", "model": "model-b"}]},
            annotations=[annotation(alice, "a-3", 10)],
        )

        result = project_metrics_payload(project, [complete_one, complete_two, incomplete], "quality")
        self.assertEqual(result["models"], ["model-b", "model-a"])
        overall = result["scopes"][0]
        self.assertEqual(overall["attempted_case_count"], 3)
        self.assertEqual(overall["complete_case_count"], 2)
        self.assertEqual(overall["dropped_case_count"], 1)

        model_b, model_a = overall["models"]
        self.assertEqual(model_a["n"], 2)
        self.assertEqual(model_a["avg"], 8.0)  # case means: 9 and 7
        self.assertEqual(model_a["median"], 8.0)
        self.assertEqual(model_a["std"], 1.0)
        self.assertEqual(model_a["tiers"]["tier_1"], {"count": 1, "pct": 50.0})
        self.assertEqual(model_a["badcase_rate"], 50.0)
        self.assertEqual(model_a["manual_badcase_rate"], 50.0)  # one of two votes is a majority by >= half
        self.assertEqual(model_a["score_hist"][8], 1)
        self.assertEqual(model_a["score_hist"][6], 1)

        self.assertEqual(model_b["avg"], 4.0)  # case means: 6 and 2
        self.assertAlmostEqual(model_b["std"], math.sqrt(4), places=2)
        self.assertEqual(model_b["badcase_rate"], 100.0)

        alice_scope = next(scope for scope in result["scopes"] if scope["label"] == "Alice")
        bob_scope = next(scope for scope in result["scopes"] if scope["label"] == "Bob")
        self.assertEqual(alice_scope["complete_case_count"], 2)
        self.assertEqual(alice_scope["dropped_case_count"], 1)
        self.assertEqual(bob_scope["complete_case_count"], 1)
        self.assertEqual(bob_scope["dropped_case_count"], 0)

    def test_empty_model_set_does_not_mark_cases_complete(self) -> None:
        project = Project(id=1, name="Empty", created_by=1, annotation_config={"dimensions": [{"key": "quality", "label": "质量", "min": 1, "max": 10}]})
        empty_case = Case(id=1, project_id=1, external_id="empty", ordinal=0, payload={"candidates": []}, annotations=[])
        result = project_metrics_payload(project, [empty_case], "quality")
        self.assertEqual(result["models"], [])
        self.assertEqual(result["scopes"][0]["complete_case_count"], 0)

    def test_old_project_uses_case_and_historical_score_dimensions(self) -> None:
        alice = User(id=1, username="alice", display_name="Alice", password_hash="x", role="annotator")
        project = Project(id=1, name="Legacy", created_by=1, annotation_config={})
        legacy_case = Case(
            id=1,
            project_id=1,
            external_id="legacy",
            ordinal=0,
            payload={
                "annotation_config": {"dimensions": [{"key": "quality", "label": "任务质量", "min": 1, "max": 10}]},
                "candidates": [{"id": "a", "model": "model-a"}],
            },
            annotations=[annotation(alice, "a", 9)],
        )

        result = project_metrics_payload(project, [legacy_case], "quality")

        self.assertEqual(result["dimension"], {"key": "quality", "label": "任务质量", "min": 1, "max": 10})
        self.assertEqual(result["scopes"][0]["complete_case_count"], 1)
        self.assertEqual(result["scopes"][0]["models"][0]["avg"], 9.0)


if __name__ == "__main__":
    unittest.main()

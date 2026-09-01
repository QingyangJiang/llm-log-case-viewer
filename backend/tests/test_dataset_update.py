from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import backend.app.main as api


def dataset_file(rows: list[dict]) -> UploadFile:
    content = "".join(f"{json.dumps(row, ensure_ascii=False)}\n" for row in rows).encode()
    return UploadFile(BytesIO(content), filename="dataset.jsonl")


class DatasetUpdateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        api.Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = api.User(username="admin", display_name="Admin", password_hash="x", role="admin")
        self.annotator = api.User(username="alice", display_name="Alice", password_hash="x", role="annotator")
        self.db.add_all([self.admin, self.annotator])
        self.db.flush()
        self.project = api.Project(name="Update", annotation_config={}, created_by=self.admin.id)
        self.db.add(self.project)
        self.db.flush()
        self.case = api.Case(
            project_id=self.project.id,
            external_id="case-1",
            ordinal=1,
            payload={
                "id": "case-1",
                "candidates": [
                    {"id": "candidate-a", "model": "model-a", "response": "old a"},
                    {"id": "candidate-b", "model": "model-b", "response": "old b"},
                ],
            },
        )
        self.db.add(self.case)
        self.db.flush()
        self.db.add(api.CaseAssignment(case_id=self.case.id, user_id=self.annotator.id, assigned_by=self.admin.id))
        self.db.add_all([
            api.Annotation(case_id=self.case.id, candidate_id="candidate-a", user_id=self.annotator.id, scores={"quality": 8}, status="submitted"),
            api.Annotation(case_id=self.case.id, candidate_id="candidate-b", user_id=self.annotator.id, scores={"quality": 6}, status="draft"),
        ])
        self.db.commit()
        self.original_case_id = self.case.id
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_data_dir = api.DATA_DIR
        api.DATA_DIR = Path(self.temp_dir.name)
        (api.DATA_DIR / "uploads").mkdir()

    def tearDown(self) -> None:
        api.DATA_DIR = self.previous_data_dir
        self.temp_dir.cleanup()
        self.db.close()
        self.engine.dispose()

    def test_update_preserves_progress_assignments_and_annotation_records(self) -> None:
        updated = {
            "id": "case-1",
            "candidates": [
                {"id": "candidate-a", "model": "model-a", "response": "new a"},
                {"id": "candidate-b-v2", "model": "model-b", "response": "new b"},
            ],
        }

        result = api.upload_jsonl(self.project.id, self.admin, self.db, dataset_file([updated]), True)

        refreshed = self.db.scalar(select(api.Case).where(api.Case.external_id == "case-1"))
        records = self.db.scalars(select(api.Annotation).order_by(api.Annotation.id)).all()
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed.id, self.original_case_id)
        self.assertEqual(refreshed.payload["candidates"][0]["response"], "new a")
        self.assertEqual([record.candidate_id for record in records], ["candidate-a", "candidate-b-v2"])
        self.assertEqual([record.status for record in records], ["submitted", "draft"])
        self.assertEqual(self.db.scalar(select(func.count(api.CaseAssignment.id))), 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["preserved_annotations"], 2)
        self.assertEqual(result["remapped_annotations"], 1)
        self.assertEqual(result["preserved_assignments"], 1)

    def test_incompatible_candidate_change_rejects_the_whole_update(self) -> None:
        incompatible = {
            "id": "case-1",
            "candidates": [
                {"id": "candidate-a", "model": "different-model", "response": "new a"},
                {"id": "candidate-b", "model": "model-b", "response": "new b"},
            ],
        }

        with self.assertRaises(HTTPException) as raised:
            api.upload_jsonl(self.project.id, self.admin, self.db, dataset_file([incompatible]), True)

        self.assertEqual(raised.exception.status_code, 409)
        self.db.expire_all()
        refreshed = self.db.get(api.Case, self.original_case_id)
        self.assertEqual(refreshed.payload["candidates"][0]["response"], "old a")
        self.assertEqual(self.db.scalar(select(func.count(api.Annotation.id))), 2)
        self.assertEqual(self.db.scalar(select(func.count(api.CaseAssignment.id))), 1)

    def test_cases_missing_from_update_file_are_retained(self) -> None:
        new_case = {
            "id": "case-2",
            "candidates": [{"id": "candidate-c", "model": "model-c", "response": "new"}],
        }

        result = api.upload_jsonl(self.project.id, self.admin, self.db, dataset_file([new_case]), True)

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["retained_not_in_file"], 1)
        self.assertEqual(self.db.scalar(select(func.count(api.Case.id))), 2)
        self.assertEqual(self.db.scalar(select(func.count(api.Annotation.id))), 2)


if __name__ == "__main__":
    unittest.main()

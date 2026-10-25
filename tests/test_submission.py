import csv
import json
from pathlib import Path

import pytest

from building_agent.submission import check_csv, load_questions, main

DATA = Path("data")
TEST_SPLIT = DATA / "test"


def fake_agent(building_directory: Path, question_text: str) -> str:
    return f"I looked at {building_directory.name}.\nAnswer: 42"


@pytest.fixture
def building(tmp_path: Path) -> Path:
    directory = tmp_path / "b1"
    directory.mkdir()
    (directory / "building.json").write_text("{}", encoding="utf-8")
    return directory


def test_test_split_from_jsonl_and_csv_agree():
    """data/test has both per-building questions.jsonl and one questions.csv: same 145 ids either way."""
    from_jsonl = load_questions(TEST_SPLIT)
    from_csv = load_questions(TEST_SPLIT / "questions.csv")
    template = [row["question_id"] for row in csv.DictReader((TEST_SPLIT / "submission_template.csv").open())]
    assert sorted(q.id for q in from_jsonl) == sorted(q.id for q in from_csv) == sorted(template)
    assert len(template) == 145
    assert all((q.building_directory / "building.json").exists() for q in from_csv)


def test_sunday_questions_json_in_one_building(building: Path):
    (building / "questions.json").write_text(
        json.dumps({"questions": [{"id": "S1", "text": "Where is the printer?", "constraints": {"step_free": True}}]}),
        encoding="utf-8",
    )
    questions = load_questions(building)
    assert [(q.id, q.building_directory, q.text) for q in questions] == [("S1", building, "Where is the printer?")]


def test_questions_file_outside_building_uses_root(building: Path, tmp_path: Path):
    path = tmp_path / "elsewhere.json"
    path.write_text(json.dumps([{"id": "S1", "building_id": "b1", "question": "How big?"}]), encoding="utf-8")
    assert load_questions(path, root=tmp_path)[0].building_directory == building


def test_end_to_end_writes_valid_csv_and_json(building: Path, tmp_path: Path, monkeypatch):
    rows = [{"id": "S1", "question": "a"}, {"id": "S2", "question": 'b,\n"quoted"'}]
    (building / "questions.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr("building_agent.submission.load_agent", lambda reference: fake_agent)
    out_csv, out_json = tmp_path / "team.csv", tmp_path / "answers.json"
    assert main([str(building), "--csv", str(out_csv), "--json", str(out_json), "--workers", "2"]) == 0
    assert [r["question_id"] for r in csv.DictReader(out_csv.open(encoding="utf-8"))] == ["S1", "S2"]
    entries = json.loads(out_json.read_text())
    assert isinstance(entries, list)  # Synera: a list of {question_id, answer}
    assert entries[1] == {"question_id": "S2", "answer": fake_agent(building, "")}
    # the official scorer must find the answer in the "answer" field, exactly as in the CSV
    from benchmark.score import committed_answer

    assert committed_answer(entries[1]["answer"]) == "42"


def test_failing_agent_still_writes_every_row_but_check_fails(building: Path, tmp_path: Path, monkeypatch):
    (building / "questions.jsonl").write_text(json.dumps({"id": "S1", "question": "a"}), encoding="utf-8")

    def broken(building_directory: Path, question_text: str) -> str:
        raise RuntimeError("API down")

    monkeypatch.setattr("building_agent.submission.load_agent", lambda reference: broken)
    out_csv = tmp_path / "team.csv"
    assert main([str(building), "--csv", str(out_csv)]) == 1
    assert out_csv.read_text(encoding="utf-8").splitlines()[1] == "S1,"


def test_check_reports_judge_problems(tmp_path: Path):
    path = tmp_path / "team.csv"
    path.write_text('question_id,answer\nA,"Answer: 1"\nA,"Answer: 2"\nZ,no answer here\n', encoding="utf-8")
    problems = " | ".join(check_csv(path, ["A", "B"]))
    for expected in ("duplicate ids", "1 question ids missing", "1 unknown ids", "without an 'Answer:' line"):
        assert expected in problems
    path.write_text("id,reply\n", encoding="utf-8")
    assert "header must be" in check_csv(path, ["A"])[0]

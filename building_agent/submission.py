"""One command from questions to a checked submission file.

  uv run --env-file .env python -m building_agent.submission data/test --csv team_synera.csv

QUESTIONS may be a split directory (data/test), one building directory, or a questions file in any of the
formats we have seen or been promised: questions.jsonl (kit), questions.csv (data/test), questions.json
(challenge brief: a list, or {"questions": [...]}, with id and text). Replies are written as the README's
question_id,answer CSV and, with --json, as answers.json. The CSV is then checked the way the judge app reads it.
The agent caches finished replies, so an interrupted run picks up where it stopped."""

import argparse
import csv
import importlib
import json
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from benchmark.score import committed_answer

BUILDING_FILE = "building.json"
QUESTION_FILES = ("questions.jsonl", "questions.json", "questions.csv")
MAX_BYTES = 5 * 1024 * 1024
COLUMNS = ("question_id", "answer")
DEFAULT_AGENT = "building_agent.agent:answer"

AgentFunction = Callable[[Path, str], str]


@dataclass(frozen=True)
class Question:
    id: str
    building_directory: Path
    text: str


def read_records(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if path.suffix == ".csv":
        return list(csv.DictReader(text.splitlines()))
    data = json.loads(text)
    return data["questions"] if isinstance(data, dict) else data


def building_directory_for(record: dict, question_file: Path, root: Path) -> Path:
    """The building a question belongs to: the folder of its questions file, else root/<building_id>, else root."""
    for candidate in (question_file.parent, root / str(record.get("building_id", "")), root):
        if (candidate / BUILDING_FILE).exists():
            return candidate
    raise ValueError(
        f"no {BUILDING_FILE} found for question {record.get('id')} (looked next to {question_file} and in {root})"
    )


def question_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    for name in QUESTION_FILES:  # one file for the whole directory (data/test/questions.csv, a Sunday questions.json)
        if (source / name).exists() and not (source / BUILDING_FILE).exists():
            return [source / name]
    found = [path for name in QUESTION_FILES for path in sorted(source.glob(name)) + sorted(source.glob(f"*/{name}"))]
    by_folder: dict[Path, Path] = {}
    for path in found:  # one file per building, preferring .jsonl
        by_folder.setdefault(path.parent, path)
    return sorted(by_folder.values())


def load_questions(source: Path, root: Path | None = None) -> list[Question]:
    root = root or (source.parent if source.is_file() else source)
    questions, seen = [], set()
    for path in question_files(source):
        for record in read_records(path):
            question_id = str(record.get("id") or record.get("question_id") or "").strip()
            text = str(record.get("question") or record.get("text") or "").strip()
            if not question_id or not text:
                raise ValueError(f"{path}: every question needs an id and a text, got {record}")
            if question_id in seen:
                continue
            seen.add(question_id)
            questions.append(Question(question_id, building_directory_for(record, path, root), text))
    if not questions:
        raise ValueError(f"no questions found in {source}")
    return questions


def load_agent(reference: str) -> AgentFunction:
    module_name, function_name = reference.split(":")
    return getattr(importlib.import_module(module_name), function_name)


def answer_all(questions: list[Question], agent: AgentFunction, workers: int = 4) -> dict[str, str]:
    """Replies by question id; a question whose agent call fails gets an empty reply and is reported."""

    def one(question: Question) -> tuple[str, str]:
        try:
            reply = agent(question.building_directory, question.text)
        except Exception as error:  # noqa: BLE001 - one failed question must not lose the other 144
            print(f"[submission] {question.id}: FAILED {type(error).__name__}: {error}", file=sys.stderr)
            reply = ""
        status = "ok" if committed_answer(reply) else "NO ANSWER LINE"
        print(f"[submission] {question.id:34s} {status}", flush=True)
        return question.id, reply

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return dict(pool.map(one, questions))


def write_csv(path: Path, questions: list[Question], replies: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows((question.id, replies.get(question.id, "")) for question in questions)


def write_json(path: Path, questions: list[Question], replies: dict[str, str]) -> None:
    """answers.json from the challenge brief: one entry per id with the full reply and its Answer: line."""
    entries = [
        {
            "id": question.id,
            "answer": committed_answer(replies.get(question.id, "")),
            "reply": replies.get(question.id, ""),
        }
        for question in questions
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"answers": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_csv(path: Path, expected_ids: list[str]) -> list[str]:
    """Problems the judge app would trip over; an empty list means the file is ready to submit."""
    problems = []
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        problems.append(f"file is {len(raw) / 1e6:.1f} MB, limit is 5 MB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        return [*problems, f"not UTF-8: {error}"]
    rows = list(csv.reader(text.splitlines(keepends=True)))
    if not rows or tuple(rows[0]) != COLUMNS:
        return [*problems, f"header must be {','.join(COLUMNS)}, got {rows[0] if rows else 'nothing'}"]
    ids = [row[0] for row in rows[1:] if row]
    if bad := [row for row in rows[1:] if row and len(row) != 2]:
        problems.append(f"{len(bad)} rows do not have exactly 2 columns, first: {bad[0][:1]}")
    if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"duplicate ids: {duplicates[:5]}")
    if missing := [i for i in expected_ids if i not in set(ids)]:
        problems.append(f"{len(missing)} question ids missing, first: {missing[:5]}")
    if extra := sorted(set(ids) - set(expected_ids)):
        problems.append(f"{len(extra)} unknown ids, first: {extra[:5]}")
    if no_answer := [row[0] for row in rows[1:] if len(row) == 2 and not committed_answer(row[1])]:
        problems.append(f"{len(no_answer)} replies without an 'Answer:' line: {no_answer[:10]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="building_agent.submission", description=__doc__.split("\n\n")[0])
    parser.add_argument("questions", type=Path, help="split dir, building dir, or questions .jsonl/.json/.csv")
    parser.add_argument("--csv", type=Path, required=True, help="submission CSV to write (or to check with --check)")
    parser.add_argument("--json", type=Path, default=None, help="also write answers.json")
    parser.add_argument(
        "--root", type=Path, default=None, help="where building folders live, if not next to the questions"
    )
    parser.add_argument("--agent", default=DEFAULT_AGENT, help=f"module:function, default {DEFAULT_AGENT}")
    parser.add_argument("--workers", type=int, default=4, help="questions answered in parallel")
    parser.add_argument("--check", action="store_true", help="only check an existing CSV against the questions")
    arguments = parser.parse_args(argv)

    questions = load_questions(arguments.questions, arguments.root)
    print(f"[submission] {len(questions)} questions in {len({q.building_directory for q in questions})} buildings")
    if not arguments.check:
        replies = answer_all(questions, load_agent(arguments.agent), arguments.workers)
        write_csv(arguments.csv, questions, replies)
        if arguments.json:
            write_json(arguments.json, questions, replies)
            print(f"[submission] wrote {arguments.json}")
    problems = check_csv(arguments.csv, [question.id for question in questions])
    for problem in problems:
        print(f"[submission] PROBLEM: {problem}", file=sys.stderr)
    verdict = "NOT ready" if problems else "ready to submit"
    print(f"[submission] {arguments.csv}: {verdict} ({arguments.csv.stat().st_size / 1e3:.0f} kB)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

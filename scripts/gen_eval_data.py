#!/usr/bin/env python3
"""生成并导入 DocMind 评测数据集，禁止 generate 自动写入数据库。

人工标注流程：generate 从 ready 文档的叶子切片生成待审核 JSONL；人工检查
question、reference_answer、expected_chunk_ids 和证据内容；确认记录改为
review_status=approved，错误记录改为 rejected；最后运行 import 执行校验和入库。

示例：
  uv run --project backend python scripts/gen_eval_data.py generate \
    --dataset-name docmind-v1 --count 40
  uv run --project backend python scripts/gen_eval_data.py import \
    --input scripts/eval_data/docmind-v1.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.session import get_async_session_factory  # noqa: E402
from app.evaluation.dataset_generation import (  # noqa: E402
    EvalDataGenerationError,
    EvalDataGenerator,
    EvidenceChunk,
    GeneratedEvalCase,
    QuestionType,
    normalize_import_records,
    question_type_counts,
)
from app.models.document import Chunk, Document  # noqa: E402
from app.models.enums import DocumentStatus  # noqa: E402
from app.models.eval_dataset import EvalDatasetItem  # noqa: E402
from app.repositories.eval import create_eval_case  # noqa: E402
from sqlalchemy import select  # noqa: E402

_NUMERIC_PATTERN = re.compile(r"[0-9０-９]|[一二三四五六七八九十百千万亿]+[年月日个项条款元]")
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "scripts" / "eval_data"


async def _load_leaf_chunks(document_names: list[str] | None = None) -> list[EvidenceChunk]:
    """只读取 ready 文档的叶子切片，和检索评测的 chunk_id 语义保持一致。"""
    statement = (
        select(Chunk, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Document.status == DocumentStatus.READY,
            Chunk.is_parent.is_(False),
        )
        .order_by(Document.created_at, Chunk.chunk_index)
    )
    if document_names:
        statement = statement.where(Document.filename.in_(document_names))
    async with get_async_session_factory()() as session:
        rows = (await session.execute(statement)).all()
    if document_names:
        found = {filename for _, filename in rows}
        missing = sorted(set(document_names) - found)
        if missing:
            raise ValueError(f"ready documents not found: {', '.join(missing)}")
    return [
        EvidenceChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=filename,
            page_number=chunk.page_number,
            heading_path=tuple(chunk.heading_path),
            content=chunk.content,
        )
        for chunk, filename in rows
    ]


def _choose_evidence(
    question_type: QuestionType,
    chunks: list[EvidenceChunk],
    rng: random.Random,
) -> list[EvidenceChunk]:
    """按题型选择证据，保证数字题含数字、对比题跨文档。"""
    by_document: dict[UUID, list[EvidenceChunk]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk.document_id].append(chunk)

    if question_type == "numeric":
        candidates = [chunk for chunk in chunks if _NUMERIC_PATTERN.search(chunk.content)]
        if not candidates:
            raise ValueError("no numeric leaf chunk found for numeric questions")
        return [rng.choice(candidates)]

    if question_type == "multi_document":
        if len(by_document) < 2:
            raise ValueError("multi_document questions require at least two ready documents")
        document_ids = rng.sample(list(by_document), 2)
        return [rng.choice(by_document[document_id]) for document_id in document_ids]

    if question_type == "out_of_kb":
        document_ids = rng.sample(list(by_document), min(2, len(by_document)))
        return [rng.choice(by_document[document_id]) for document_id in document_ids]

    return [rng.choice(chunks)]


async def _generate(args: argparse.Namespace) -> int:
    output = args.output or _DEFAULT_OUTPUT_DIR / f"{args.dataset_name}.jsonl"
    if output.exists() and not args.overwrite:
        raise FileExistsError(f"output already exists: {output}; use --overwrite")

    chunks = await _load_leaf_chunks(args.document_name)
    if not chunks:
        raise ValueError("no ready leaf chunks found; upload and parse documents first")

    rng = random.Random(args.seed)
    generator = EvalDataGenerator(max_retries=args.max_retries)
    counts = question_type_counts(args.count)
    records: list[GeneratedEvalCase] = []
    existing_questions: list[str] = []
    skipped = 0

    for question_type, count in counts.items():
        for _index in range(count):
            evidence = _choose_evidence(question_type, chunks, rng)
            try:
                record = await generator.generate(
                    dataset_name=args.dataset_name,
                    question_type=question_type,
                    evidence=evidence,
                    existing_questions=existing_questions,
                    created_by=args.created_by,
                )
            except EvalDataGenerationError as exc:
                skipped += 1
                print(f"[跳过] {question_type}: {exc}")
                continue
            records.append(record)
            existing_questions.append(record.question)
            print(f"[{len(records)}/{args.count}] {question_type}: {record.question}")

    if not records:
        raise ValueError("no eval cases generated; check LLM output and evidence diversity")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    print(f"\n已生成 {len(records)} 条待审核样本（跳过 {skipped} 条）：{output}")
    print("请人工校对，并将确认记录改为 review_status=approved 后再执行 import。")
    return 0


def _read_approved_records(path: Path) -> list[GeneratedEvalCase]:
    records: list[GeneratedEvalCase] = []
    pending = 0
    rejected = 0
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                record = GeneratedEvalCase.model_validate(payload)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
            if record.review_status == "approved":
                records.append(record)
            elif record.review_status == "rejected":
                rejected += 1
            else:
                pending += 1
    if not records:
        raise ValueError("no approved records found; complete manual review first")
    print(f"读取 approved={len(records)}, pending={pending}, rejected={rejected}")
    return records


async def _import(args: argparse.Namespace) -> int:
    records = normalize_import_records(
        _read_approved_records(args.input),
        dataset_override=args.dataset_name,
        created_by_override=args.created_by,
    )
    expected_ids = {chunk_id for record in records for chunk_id in record.expected_chunk_ids}

    async with get_async_session_factory()() as session:
        existing_chunk_ids = set(
            await session.scalars(
                select(Chunk.id)
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    Chunk.id.in_(expected_ids),
                    Chunk.is_parent.is_(False),
                    Document.status == DocumentStatus.READY,
                )
            )
        )
        missing_ids = sorted(str(chunk_id) for chunk_id in expected_ids - existing_chunk_ids)
        if missing_ids:
            raise ValueError(f"expected chunks do not exist: {', '.join(missing_ids)}")

        existing_questions = set(
            await session.scalars(
                select(EvalDatasetItem.question).where(
                    EvalDatasetItem.dataset_name == records[0].dataset_name
                )
            )
        )
        imported = 0
        for record in records:
            if record.question in existing_questions:
                print(f"跳过重复问题：{record.question}")
                continue
            await create_eval_case(
                session,
                dataset_name=record.dataset_name,
                question=record.question,
                reference_answer=record.reference_answer,
                expected_chunk_ids=record.expected_chunk_ids,
                tags=list(dict.fromkeys([*record.tags, record.question_type])),
                created_by=record.created_by,
            )
            existing_questions.add(record.question)
            imported += 1

    print(f"导入完成：dataset={records[0].dataset_name}, imported={imported}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成和导入 DocMind 评测数据")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="生成待人工审核的 JSONL")
    generate.add_argument("--dataset-name", required=True)
    generate.add_argument("--count", type=int, default=40)
    generate.add_argument("--output", type=Path)
    generate.add_argument(
        "--document-name",
        action="append",
        help="只使用指定文件名，可重复传入多个 --document-name",
    )
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--max-retries", type=int, default=1)
    generate.add_argument("--created-by", default="llm-assisted")
    generate.add_argument("--overwrite", action="store_true")

    import_command = subparsers.add_parser("import", help="仅导入 approved 记录")
    import_command.add_argument("--input", type=Path, required=True)
    import_command.add_argument("--dataset-name")
    import_command.add_argument("--created-by")
    return parser


def main() -> int:
    stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
    stderr_reconfigure = getattr(sys.stderr, "reconfigure", None)
    if stdout_reconfigure is not None:
        stdout_reconfigure(encoding="utf-8")
    if stderr_reconfigure is not None:
        stderr_reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        if args.command == "generate":
            return asyncio.run(_generate(args))
        return asyncio.run(_import(args))
    except (FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

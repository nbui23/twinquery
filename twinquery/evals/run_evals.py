"""Run deterministic TwinQuery agent evaluations."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from twinquery.agents.graph import run_agent_query
from twinquery.evals.rubric import CRITERIA, score_example


BENCHMARK_PATH = Path(__file__).with_name("benchmark_questions.jsonl")
OUTPUT_PATH = Path(__file__).with_name("results.csv")


def load_questions(path: Path = BENCHMARK_PATH, limit: int | None = None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def mock_llm(prompt: str) -> str:
    question = prompt.lower()
    if "within" in question or "near downtown" in question:
        return (
            "SELECT id, name, city FROM buildings "
            "WHERE ST_DWithin(centroid::geography, ST_SetSRID(ST_MakePoint(-75.6972, 45.4215), 4326)::geography, 3000) "
            "LIMIT 25;"
        )
    if "benchmark" in question:
        return (
            "SELECT b.building_type, AVG(b.estimated_energy_intensity_kwh_m2) AS avg_kwh_m2_year "
            "FROM buildings b JOIN energy_benchmarks eb ON eb.building_type = b.building_type "
            "GROUP BY b.building_type;"
        )
    if "payback" in question:
        return "SELECT measure_type, payback_years FROM retrofit_measures ORDER BY payback_years ASC LIMIT 25;"
    if "built before 1980" in question or "older buildings" in question:
        return "SELECT id, name, year_built FROM buildings WHERE year_built < 1980 LIMIT 25;"
    if "emission" in question:
        return "SELECT id, name, heating_fuel, ghg_emissions_kgco2e_year FROM buildings ORDER BY ghg_emissions_kgco2e_year DESC LIMIT 25;"
    if "natural gas" in question or "oil" in question or "propane" in question:
        return "SELECT id, name, heating_fuel FROM buildings WHERE heating_fuel IN ('natural_gas', 'heating_oil', 'propane') LIMIT 25;"
    if "municipal" in question:
        return "SELECT id, name, owner_type, retrofit_priority_score FROM buildings WHERE owner_type = 'municipal' LIMIT 25;"
    if "cities" in question:
        return "SELECT city, COUNT(*) AS building_count FROM buildings GROUP BY city;"
    if "priority" in question or "retrofitted" in question or "retrofit" in question:
        return "SELECT id, name, building_type, retrofit_priority_score FROM buildings ORDER BY retrofit_priority_score DESC LIMIT 25;"
    return (
        "SELECT id, name, building_type, estimated_energy_intensity_kwh_m2 AS kwh_m2_year "
        "FROM buildings ORDER BY kwh_m2_year DESC LIMIT 25;"
    )


def mock_query_runner(sql: str) -> list[dict[str, Any]]:
    return [{"name": "Synthetic Office 001", "building_type": "office", "retrofit_priority_score": 82.5}]


def mock_retriever(question: str) -> list[dict[str, Any]]:
    text = question.lower()
    if "heat pump" in text or "oil" in text or "propane" in text:
        source = "heat_pump_notes.md"
        body = "Heat pump feasibility depends on fuel type, emissions, load, and electrical capacity."
    elif "envelope" in text or "older" in text:
        source = "building_envelope_retrofits.md"
        body = "Envelope retrofit screening should consider age, air leakage, insulation, and uncertainty."
    elif "benchmark" in text or "energy intensity" in text:
        source = "energy_benchmarking_notes.md"
        body = "Energy intensity benchmarks are directional and should be grouped by building type."
    elif "digital twin" in text or "lineage" in text:
        source = "digital_twin_notes.md"
        body = "Digital twin workflows should preserve data lineage and uncertainty."
    else:
        source = "retrofit_guidelines.md"
        body = "Retrofit guidance should cite observed data and avoid unsupported savings claims."
    return [{"source": source, "section": "Mock Eval Context", "text": body, "score": 1.0}]


def run_one(example: dict[str, Any], skip_llm: bool) -> dict[str, Any]:
    if skip_llm:
        state = run_agent_query(
            example["question"],
            llm_generate=mock_llm,
            query_runner=mock_query_runner,
            retriever=mock_retriever,
        )
    else:
        state = run_agent_query(example["question"])
    score = score_example(example, state)
    return {"example": example, "state": state, "score": score}


def write_csv(results: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "category",
        "question",
        "total_score",
        "max_score",
        "total_pct",
        *CRITERIA,
        "generated_sql",
        "errors",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            example = item["example"]
            state = item["state"]
            score = item["score"]
            writer.writerow(
                {
                    "id": example["id"],
                    "category": example["category"],
                    "question": example["question"],
                    "generated_sql": state.get("generated_sql", ""),
                    "errors": "; ".join(state.get("errors", [])),
                    **score,
                }
            )


def print_summary(results: list[dict[str, Any]]) -> None:
    if not results:
        print("No eval examples ran.")
        return

    mean = sum(item["score"]["total_pct"] for item in results) / len(results)
    by_category: dict[str, list[float]] = defaultdict(list)
    failures: Counter[str] = Counter()

    for item in results:
        category = item["example"]["category"]
        by_category[category].append(item["score"]["total_pct"])
        for criterion in CRITERIA:
            if not item["score"][criterion]:
                failures[criterion] += 1

    print(f"Mean total score: {mean:.3f}")
    print("Score by category:")
    for category, values in sorted(by_category.items()):
        print(f"  {category}: {sum(values) / len(values):.3f} ({len(values)} examples)")
    print("Failure counts by criterion:")
    for criterion in CRITERIA:
        print(f"  {criterion}: {failures[criterion]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TwinQuery benchmark evals.")
    parser.add_argument("--benchmark-file", type=Path, default=BENCHMARK_PATH)
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--skip-llm", action="store_true", help="Use deterministic mocked SQL generation and DB rows.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model

    examples = load_questions(args.benchmark_file, limit=args.limit)
    results = [run_one(example, skip_llm=args.skip_llm) for example in examples]
    write_csv(results, args.output_csv)
    print_summary(results)
    print(f"Saved CSV: {args.output_csv}")


if __name__ == "__main__":
    main()

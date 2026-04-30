# TwinQuery Evaluation Report

## Methodology

TwinQuery uses a deterministic benchmark to evaluate the local agent pipeline.
Each example is labelled by category and includes expected SQL patterns,
forbidden SQL patterns, expected document sources, expected terms, or expected
unsupported behavior.

The runner executes the LangGraph agent, applies a deterministic rubric, writes
per-example results to CSV, and prints aggregate scores.

## Benchmark Categories

- `structured_data_query`: building-stock SQL questions over PostgreSQL/PostGIS.
- `document_policy_query`: local RAG questions over retrofit and digital-twin notes.
- `hybrid_query`: questions requiring both database rows and document context.
- `unsupported`: requests outside TwinQuery scope or unsafe database actions.

## Metrics

- `sql_is_readonly`
- `sql_uses_relevant_table`
- `sql_uses_postgis_when_needed`
- `answer_mentions_data_limitations`
- `answer_uses_retrieved_sources_when_needed`
- `avoids_unsupported_claims`
- `handles_unsupported_question_safely`

Each criterion is scored as 0 or 1. `total_pct` is the mean criterion score for
one example.

## Initial Results Placeholder

Run:

```bash
python -m twinquery.evals.run_evals --skip-llm
```

Results are written to:

```text
twinquery/evals/results.csv
```

## Known Limitations

- Pattern matching cannot prove semantic SQL correctness.
- Mock mode measures orchestration and rubric behavior, not live LLM quality.
- Live LLM mode depends on local Ollama model behavior and database state.
- RAG citation checks verify source filenames, not full factual entailment.
- Synthetic data supports portfolio demos, not real retrofit decisions.

## Future Improvements

- Add golden SQL references and SQL execution-result checks.
- Add mutation tests for prompt-injection and SQL injection attempts.
- Add answer faithfulness checks with local evaluator models.
- Track latency, token/model metadata, and retrieval score distributions.
- Add regression thresholds for CI.

# Design Review

A structural analysis of the application, considered through two complementary lenses:

- **Rich Hickey** — *Simple Made Easy*: identify what has been complected (tangled together) that is inherently separate; pull it apart.
- **Linus Torvalds** — data structures first: "Show me your data structures and I won't usually need your code." Bad data structures force complexity into code; the right structures make the code obvious.

This is not a bug report. It is an analysis of where the design carries incidental complexity that will compound as the system grows.

---

## The Central Problem: `FlowExecution` is doing too much

`FlowExecution` is the load-bearing model. Everything touches it. And it is complected in three distinct ways.

### 1. It conflates two different domain concepts

A **data processing pipeline** (ingest → validate → transform → aggregate) and a **credit prediction** (1-row input → score) are structurally different operations. They have different:

- Input shapes (multi-row CSV vs 1-row form)
- Step counts (4 steps vs 2 steps)
- Output shapes (aggregate Parquet vs score/classification/confidence)
- Display logic (results preview vs prediction card)
- S3 path conventions (`data-processing/` vs `credit-prediction/`)

They currently share one table, discriminated only by `flow_name = "pipeline"` or `"predict_pipeline"` — a string where a structural distinction is needed.

The consequence: every query, every template, every view has to branch on `flow_name`. The comparison view digs into `parameters` with `.get("score")` — a schema that only exists by convention.

**Hickey:** these two things have been complected. They share plumbing but not semantics. Untangle them.
**Torvalds:** a string discriminator is the wrong data structure for a type distinction. Two things, two structures.

### 2. `parameters` is a schemaless blob serving two masters

**Partially resolved.** Prediction inputs (`income`, `age`, `credit_score`, `employment_years`) have been migrated to typed fields directly on `FlowExecution`. `PredictionResult` now exists as a typed relation for results (score, classification, confidence). The `parameters` JSONField is kept for backwards compatibility only — it carries a comment "do not add new keys".

**Remaining:** `FlowExecution.parameters` still exists and still contains legacy data for older records. New code should not read or write it. The end state (tracked in BL-028) is removing the field once all reads are migrated to `PredictionResult` and the typed input fields.

### 3. ~~Status is a string pretending to be a state machine~~ **Resolved**

`ExecutionStatus` is now a `TextChoices` enum with an explicit transition graph:

```python
_EXECUTION_STATUS_TRANSITIONS = {
    PENDING:   {RUNNING, FAILED},
    RUNNING:   {COMPLETED, FAILED},
    COMPLETED: set(),
    FAILED:    set(),
}
```

All status changes go through `FlowExecution.transition()`, which raises `ValueError` for illegal moves and auto-sets `completed_at`. The state machine is encoded as a data structure.

---

## The Missing Entities

Three entities were identified as missing. Two have since been added.

### ~~Missing: `ExecutionStep`~~ **Resolved**

`ExecutionStep` now exists with `status (TextChoices)`, `step_name`, `step_index`, `step_type (NOTEBOOK|MOJO)`, `started_at`, `completed_at`, `output_s3_path`, and `error_message`. Per-step progress is surfaced in the execution detail view.

### Missing: `ScoringModel`

The credit scoring algorithm — weights (0.40, 0.30, 0.20, 0.10), normalisation ranges, and classification thresholds (0.70, 0.50) — is embedded as literal numbers in `notebooks/steps/predict_02_score.ipynb`.

This means:
- There is no record of *which version of the model* produced a given score
- Changing the weights requires editing a notebook — the change is not traceable in the data layer
- Two predictions made before and after a weight change are indistinguishable
- A/B testing different scoring strategies is structurally impossible

The right data structure:

```
ScoringModel {
    id            PK
    version       VARCHAR    -- e.g. "v1.0", "v1.1"
    description   TEXT
    weights       JSON       -- {credit_score: 0.40, income: 0.30, ...}
    thresholds    JSON       -- {approved: 0.70, review: 0.50}
    is_active     BOOLEAN
    created_at    DATETIME
    created_by    FK → USER
}
```

`PredictionResult` (or `FlowExecution`) then carries a `scoring_model_id FK` — every score is permanently linked to the model version that produced it.

**Hickey:** the algorithm is currently complected with the execution. The *what* (score this applicant) and the *how* (these specific weights, right now, in this notebook) are one thing. They should be two.

**Torvalds:** a model version is data. Make it a data structure.

### ~~Missing: `PredictionResult`~~ **Resolved**

`PredictionResult` now exists as a typed `OneToOne` relation on `FlowExecution` with `score (FLOAT)`, `classification (TextChoices)`, `confidence (FLOAT)`, and `scored_at`. The comparison view joins this relation rather than inspecting the parameters blob.

The `scoring_model FK` is not yet implemented — see Missing: `ScoringModel` below.

The original design:

```
PredictionResult {
    id              PK
    execution_id    FK → FlowExecution (OneToOne)
    scoring_model   FK → ScoringModel (not yet implemented)
    score           FLOAT
    classification  VARCHAR  -- "Approved" | "Review" | "Declined"
    confidence      FLOAT
    scored_at       DATETIME
}
```

With this structure:
- The input values stay in `FlowExecution.parameters` (or a dedicated `PredictionInput` table) — immutable after submission
- Results are a separate, typed, indexed relation
- `classification="Declined"` is a real database column — queryable, aggregatable, filterable without JSON gymnastics
- The comparison view becomes a simple JOIN, not a blob inspection

---

## ~~The Notebook ↔ Application Interface~~ **Resolved**

The stdout-scraping approach has been replaced. Notebooks now write a `result.json` manifest to a known S3 path (`processed/flows/<pipeline>/{run_id}/result.json`). `PipelineRunner._read_result_json()` reads that file after the subprocess exits. The contract is a file at a predictable path, not a parsing convention over stdout.

---

## Concrete Security Issue: SQL Interpolation in `DataLakeAnalytics`

`services/datalake.py` line 22:

```python
self.conn.execute(f"""
    CREATE SECRET datalake_s3 (
        TYPE S3,
        KEY_ID '{settings.AWS_ACCESS_KEY_ID}',
        SECRET '{settings.AWS_SECRET_ACCESS_KEY}',
        ...
    )
""")
```

Credentials are interpolated directly into a DuckDB SQL string via f-string. While DuckDB's `CREATE SECRET` likely doesn't support parameterised queries, this pattern is dangerous as a convention — it normalises credential interpolation into SQL strings. The values should at minimum be validated/sanitised, and the approach should be documented as a known limitation, not a pattern to follow elsewhere. Tracked in BL-022 (secrets audit).

---

## Summary of Structural Improvements

| Problem | Hickey diagnosis | Torvalds fix |
|---------|-----------------|--------------|
| `FlowExecution` serves two types | Complects pipeline + prediction | Two models (or a discriminated union with separate result tables) |
| `parameters` stores inputs + outputs | Complects values from different points in time | `PredictionResult` table with typed columns |
| No step tracking | Pipeline complexity hidden in stdout parsing | `ExecutionStep` table |
| Scoring weights in notebook code | Algorithm complected with execution | `ScoringModel` table; notebook reads config from it |
| `status` is an unguarded string | State machine is implicit | `TextChoices` + transition guards |
| Stdout as result protocol | Communication complected with computation | Write `result.json` to S3; Django reads it |

None of these are urgent rewrites. They are the structural work that, if deferred too long, makes every future feature harder. The `ExecutionStep` entity in particular unlocks a whole class of UX (per-step progress, step-level retry, performance analytics) that is currently impossible at the data layer.

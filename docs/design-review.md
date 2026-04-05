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

`parameters` (JSONField) currently stores:

- **Prediction inputs** at submission time: `{income, age, credit_score, employment_years}`
- **Prediction results** after completion: `{..., score, classification, confidence}`

These are logically separate — inputs are immutable after submission; results are written once on completion. But they are merged into one mutable blob via `.update(parameters={**execution.parameters, "score": ...})`.

Consequences:
- No schema enforcement — a typo in a key silently produces a `None` in the UI
- No queryability — finding all "Declined" predictions requires `parameters__classification="Declined"` JSON field lookups, which don't use standard indexes
- No audit trail — there is no record of what the inputs *were* at the time of scoring vs what was updated afterwards
- The comparison view (`comparison.html`) must know the internal key names to extract values

**Hickey:** inputs and outputs are different values at different points in time. They have been complected into one place.
**Torvalds:** the right data structure makes the schema explicit and queryable. A `PredictionResult` row with typed columns (`score FLOAT`, `classification VARCHAR`, `confidence FLOAT`) makes every downstream query trivial.

### 3. Status is a string pretending to be a state machine

```python
status = models.CharField(max_length=50, default="PENDING")
```

There are no `choices`. The valid values (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`) and valid transitions are known only by reading `tasks.py`. Nothing at the data layer prevents:

- Setting status to `"COMPLETED"` while `completed_at` is null
- Transitioning from `FAILED` back to `RUNNING`
- A typo producing `"COMPELTED"` that never matches any template branch

The state machine is real — it governs the entire UI polling loop. But it is implicit, unencoded, and unguarded.

**Torvalds:** the state machine is a data structure. Encode it as one.

---

## The Missing Entities

Reading the data model (`data-model.mmd`) reveals three entities that the domain clearly needs but that do not exist.

### Missing: `ExecutionStep`

A data processing pipeline has four discrete steps: ingest, validate, transform, aggregate. Currently:

- A pipeline execution is either `PENDING`, `RUNNING`, `COMPLETED`, or `FAILED` — with no visibility into which step is running or which step failed
- The step-level notebook output files exist in S3 (e.g. `{run_id}_01_ingest.ipynb`) but their status is never surfaced to the application
- When a pipeline fails at step 3, the user sees "FAILED" with a 2000-character truncated error — they cannot tell that steps 1 and 2 succeeded

The right data structure:

```
ExecutionStep {
    execution_id FK → FlowExecution
    step_name     VARCHAR    -- "ingest" | "validate" | "transform" | "aggregate"
    step_index    SMALLINT   -- ordering
    status        TextChoices
    started_at    DATETIME
    completed_at  DATETIME
    output_s3_path VARCHAR   -- path to the step's output notebook
    error_message TEXT
}
```

This structure makes per-step progress trivially displayable, makes failure diagnosis accurate, and makes performance analytics possible ("how long does validation take on average across all runs?").

**Torvalds:** the domain has steps. The data model should too. Without this entity, the complexity of tracking progress is pushed into: the notebook stdout protocol, the UI polling loop, and the truncated error message.

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

### Missing: `PredictionResult`

Prediction outputs are currently appended to `FlowExecution.parameters`. The right data structure separates them:

```
PredictionResult {
    id              PK
    execution_id    FK → FlowExecution (OneToOne)
    scoring_model   FK → ScoringModel
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

## The Notebook ↔ Application Interface

`PipelineRunner._extract_metadata()` in `runner.py`:

```python
for line in reversed(stdout.splitlines()):
    line = line.strip()
    if line.startswith("{"):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
return {}
```

The contract between the notebook and the application is: *print valid JSON as the last line of stdout*. This is fragile:
- Any library that prints a dict-like string (e.g. a Polars schema repr) can silently produce the wrong metadata
- The contract is invisible to future notebook authors — it is in a comment (`# IMPORTANT: ...`) not in an interface
- The channel (stdout) carries both logging noise and structured data — separating them requires the backwards scan

**Hickey:** computation (score the applicant) is complected with signalling (communicate the result to Django). These are separate concerns.

A more robust alternative: notebooks write a `result.json` manifest to a known S3 path (`{run_id}/result.json`). Django reads that path after the subprocess exits. The contract is a file, not a parsing convention.

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

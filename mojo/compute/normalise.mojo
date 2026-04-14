"""
normalise.mojo — feature normalisation over large datasets.

Entry point: fn main() raises
Environment variables (set by mojo-compute server):
  RUN_ID    — pipeline run UUID
  S3_INPUT  — full S3 URL to input Parquet (s3://bucket/key)
  S3_OUTPUT — full S3 URL prefix for output Parquet + result.json

AWS credentials flow through the standard credential chain
(AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) — never passed as parameters.

Data I/O uses a thin Python shim via Mojo's Python interop until Mojo gains
native Parquet support.

Output protocol (BL-029):
  {s3_output}/normalised.parquet
  {s3_output}/result.json  — {"row_count": N, "s3_output_path": "..."}
"""

from python import Python


fn main() raises:
    let os = Python.import_module("os")
    let json = Python.import_module("json")

    let run_id = os.environ.get("RUN_ID", "")
    let s3_input = os.environ.get("S3_INPUT", "")
    let s3_output = os.environ.get("S3_OUTPUT", "")

    print("normalise.mojo starting: run_id=" + str(run_id))
    print("  s3_input  =", s3_input)
    print("  s3_output =", s3_output)

    # --- Data I/O via Python interop ----------------------------------------
    let s3fs = Python.import_module("s3fs")
    let polars = Python.import_module("polars")

    # Read input Parquet from S3
    let fs = s3fs.S3FileSystem()
    let df = polars.read_parquet(s3_input)

    print("  rows loaded:", df.height)

    # --- Feature normalisation -----------------------------------------------
    # Normalise all numeric columns to [0, 1] range.
    let numeric_cols = df.select(polars.selectors.numeric()).columns

    var out_df = df
    for col in numeric_cols:
        let col_min = df[col].min()
        let col_max = df[col].max()
        let col_range = col_max - col_min
        if col_range != 0:
            out_df = out_df.with_columns(
                ((polars.col(col) - col_min) / col_range).alias(col)
            )

    # --- Write output to S3 --------------------------------------------------
    let output_parquet = str(s3_output) + "/normalised.parquet"
    let result_path = str(s3_output) + "/result.json"

    out_df.write_parquet(output_parquet)

    let result = json.dumps(
        {"row_count": df.height, "s3_output_path": output_parquet}
    )

    with fs.open(result_path, "w") as f:
        _ = f.write(result)

    print("normalise.mojo complete:", output_parquet)

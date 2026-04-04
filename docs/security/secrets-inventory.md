# Secrets Inventory

All secrets used by the application, where they are stored, how they are injected, and how to rotate each.

**Reference:** OWASP ASVS v4.0 §2.10.4; OWASP Secrets Management Cheat Sheet.

---

## Inventory

### DJANGO_SECRET_KEY

| | |
|---|---|
| **Purpose** | Django's cryptographic signing key — sessions, CSRF tokens, signed cookies |
| **Used in** | `backend/config/settings/base.py` via `env("DJANGO_SECRET_KEY")` |
| **Dev value** | Set in `.env` (gitignored) |
| **Production** | `op://Production/App/django_secret_key` → injected via `op inject` into `/opt/app/.env.production` |
| **CI** | `DJANGO_SECRET_KEY: ci-secret-key-not-for-production` (hardcoded in workflow — safe; CI key is never used for signing real data) |
| **Rotation** | Generate a new 50-char random string. Update 1Password, run `just prod-deploy`. All existing sessions are immediately invalidated — users must log in again. No database migration required. |

---

### DATABASE_URL / DB_PASSWORD

| | |
|---|---|
| **Purpose** | PostgreSQL connection string for Django and Celery |
| **Used in** | `settings/base.py` via `env.db("DATABASE_URL")` |
| **Dev value** | `postgresql://django:django_password@db:5432/django_prefect` — placeholder, local only |
| **Production** | `op://Production/App/db_password` composed into `DATABASE_URL` in `.env.tpl` |
| **CI** | Service container uses `POSTGRES_PASSWORD: django_password` — ephemeral, destroyed after job |
| **Rotation** | 1. Update password in PostgreSQL: `ALTER USER app PASSWORD 'new';` 2. Update `op://Production/App/db_password` in 1Password. 3. Run `just prod-deploy` (triggers `push-env` re-injection). Brief connection errors during restart; Swarm rolling update minimises downtime. |

---

### AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

| | |
|---|---|
| **Purpose** | S3 data lake access (upload, download, presigned URLs, DuckDB queries) |
| **Used in** | `settings/base.py`; inherited by notebook subprocess via `os.environ`; DuckDB `CREATE SECRET` in `services/datalake.py` |
| **Dev value** | `rustfs` / `rustfs_secret` — RustFS local credentials, not real AWS |
| **Production** | `op://Production/AWS/access_key_id` and `op://Production/AWS/secret_access_key` |
| **CI** | `AWS_ACCESS_KEY_ID: test` / `AWS_SECRET_ACCESS_KEY: test` — moto intercepts all S3 calls in tests |
| **Not passed as** | Papermill parameters or `PIPELINE_PARAMS` — credentials flow via `**os.environ` only |
| **Known limitation** | `services/datalake.py` interpolates these into a DuckDB f-string (no parameterised query support in DuckDB `CREATE SECRET`); values come from settings, not user input |
| **Rotation** | 1. Create new IAM access key in AWS Console. 2. Update `op://Production/AWS/` fields. 3. Run `just prod-deploy`. 4. Delete old IAM key. Zero downtime if done in order. |

---

### REDIS_URL / CELERY_BROKER_URL

| | |
|---|---|
| **Purpose** | Celery task broker and Django cache backend |
| **Used in** | `settings/base.py` via `env()` |
| **Dev value** | `redis://localhost:6379/0` — unauthenticated local Redis |
| **Production** | `redis://redis:6379/0` — internal overlay network, not exposed externally; no auth configured |
| **Rotation** | If Redis auth is added: update URL, redeploy. No persistent data loss (Celery tasks are transient; cache is ephemeral). |

---

### EMAIL_HOST_PASSWORD

| | |
|---|---|
| **Purpose** | SMTP authentication for transactional email (failure notifications, registration confirmation) |
| **Used in** | `settings/base.py` via `env()` |
| **Dev value** | Not set (email backend defaults to console in development) |
| **Production** | `op://Production/App/email_password` |
| **Rotation** | Update SMTP credentials in provider, update 1Password, run `just prod-deploy`. |

---

### PROD_SSH_KEY (GitHub Actions)

| | |
|---|---|
| **Purpose** | SSH private key used by GitHub Actions `deploy` job to connect to the production EC2 instance |
| **Used in** | `.github/workflows/deploy.yml` via `${{ secrets.PROD_SSH_KEY }}` |
| **Stored** | GitHub repository secret (never in the repo or 1Password) |
| **Rotation** | 1. Generate new ED25519 key pair. 2. Add public key to `~/.ssh/authorized_keys` on EC2 host alongside old key. 3. Update `PROD_SSH_KEY` GitHub secret. 4. Verify a deploy succeeds. 5. Remove old public key from EC2. |

---

### PROD_HOST / PROD_USER (GitHub Actions)

| | |
|---|---|
| **Purpose** | Production EC2 Elastic IP and SSH username for the deploy job |
| **Used in** | `.github/workflows/deploy.yml` via `${{ secrets.PROD_HOST }}` and `${{ secrets.PROD_USER }}` |
| **Stored** | GitHub repository secrets |
| **Rotation** | Update after any infrastructure change that changes the Elastic IP (rare; EIP is stable). |

---

### OP_SERVICE_ACCOUNT_TOKEN

| | |
|---|---|
| **Purpose** | Allows the 1Password Terraform provider to read the SSH public key from the Production vault |
| **Used in** | Exported locally before running `just prod-tf-*` commands; never stored in files |
| **Stored** | In 1Password at `op://Private/Terraform SA/token` |
| **Rotation** | Regenerate service account token in 1Password Developer Tools. Update local export. |

---

## Audit Findings (as of 2026-04-04)

| Area | Status | Notes |
|------|--------|-------|
| Source code scan (gitleaks) | Not yet run | Add to CI — see BL-022 |
| Notebook injected-parameters | Resolved | `runner.py` and all notebooks fixed — credentials never passed as papermill params |
| `justfile run-pipeline` | Resolved | Credentials removed from `PIPELINE_PARAMS` |
| `docker-compose.yml` | Acceptable | `django_password` / `rustfs_secret` are local dev placeholders; not real secrets |
| `docker-compose.staging.yml` | Acceptable | Uses `.env` file injection; no plaintext secrets committed |
| GitHub Actions | Clean | All secrets use `${{ secrets.* }}`; no values echoed to logs |
| Django log config (production) | Clean | Structured logging to stdout; no credential fields logged |
| Password hashing | Resolved | `PASSWORD_HASHERS` explicitly set to Argon2id with PBKDF2 fallback (ASVS 2.10.3) |
| DuckDB f-string interpolation | Documented | Known limitation; values from trusted settings only; comment added to `datalake.py` |
| Model fields | Clean | No plaintext token or password fields; Django auth hashes passwords |

---

## Adding a new secret

1. Add the value to 1Password in the **Production** vault under the appropriate item
2. Add the `{{ op://... }}` reference to `deploy/.env.tpl`
3. Add `env("NEW_VAR")` to `backend/config/settings/base.py`
4. Update this inventory with purpose, injection path, and rotation procedure
5. Run `just prod-deploy` to inject the new value

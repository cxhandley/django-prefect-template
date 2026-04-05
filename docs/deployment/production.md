# Production Environment

Production runs Docker Swarm on a single EC2 instance (upgradeable to multi-node). Infrastructure is provisioned with Terraform; secrets are managed by 1Password; deploys are triggered via `just`.

## Architecture

```
Internet → Traefik (80/443, Let's Encrypt) → Django web (2 replicas, gunicorn)
                                           → Celery worker (2 replicas)
                                           → Flower (SSH tunnel only)
           PostgreSQL (container, nightly pg_dump → S3)
           Redis (container)
           S3 / RustFS (data lake) — or AWS S3 directly
```

All services run in a Docker Swarm overlay network on a single `t3.medium` EC2 instance in `ap-southeast-2` (Sydney). The Elastic IP is stable across instance restarts.

---

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| `terraform >= 1.7` | Provision AWS infra | [terraform.io](https://developer.hashicorp.com/terraform/install) |
| `op` CLI | 1Password secrets | [1password.com/downloads/command-line](https://developer.1password.com/docs/cli/get-started/) |
| `aws` CLI | Authenticate to AWS | [aws.amazon.com/cli](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) |
| `just` | Task runner | `brew install just` |
| SSH key | EC2 access | See [1Password SSH setup](#1password-ssh-key-setup) |

---

## 1Password Setup

### Service account (for Terraform)

1. Go to **1Password.com → Developer Tools → Service Accounts**
2. Create a service account with read access to the **Production** vault
3. Store the token in 1Password: `op://Private/Terraform SA/token`
4. Export before running Terraform commands:
   ```bash
   export OP_SERVICE_ACCOUNT_TOKEN=$(op read "op://Private/Terraform SA/token")
   ```

### SSH key setup

1. Generate an ED25519 key pair:
   ```bash
   ssh-keygen -t ed25519 -C "production-deploy" -f ~/.ssh/id_ed25519_prod
   ```
2. In 1Password, create an item **Infrastructure** in the **Production** vault
3. Add a field `public_key` with the contents of `~/.ssh/id_ed25519_prod.pub`
4. Terraform reads this field to create the EC2 key pair — no key material in the repo

### Production vault items

Create these items in the **Production** 1Password vault before running `push-env`:

**Item: App**
| Field | Value |
|-------|-------|
| `django_secret_key` | 50-char random string |
| `db_password` | strong random password |
| `data_lake_bucket` | S3 bucket name for pipeline data |
| `backup_bucket` | copy from `just prod-tf-outputs` after apply |
| `production_host` | copy from `just prod-tf-outputs` after apply |
| `ghcr_repo` | `my-org/my-repo` |
| `email_host` | SMTP host (e.g. `email-smtp.ap-southeast-2.amazonaws.com`) |
| `email_user` | SMTP username |
| `email_password` | SMTP password |
| `from_email` | `noreply@yourdomain.com` |

**Item: AWS**
| Field | Value |
|-------|-------|
| `access_key_id` | IAM access key for S3 data lake access |
| `secret_access_key` | IAM secret key |

**Item: GHCR**
| Field | Value |
|-------|-------|
| `token` | GitHub personal access token with `read:packages` scope |

---

## First-time provisioning

### 1. Bootstrap Terraform remote state

Create the S3 bucket for Terraform state manually (chicken-and-egg: Terraform can't manage its own state bucket):

```bash
aws s3 mb s3://my-org-tfstate --region ap-southeast-2
aws s3api put-bucket-versioning \
    --bucket my-org-tfstate \
    --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption \
    --bucket my-org-tfstate \
    --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

### 2. Configure Terraform

```bash
cp terraform/backend.hcl.example terraform/backend.hcl    # fill in bucket name
cp terraform/terraform.tfvars.example terraform/terraform.tfvars  # fill in your IP
```

Edit `terraform/terraform.tfvars`:
```hcl
ssh_allowed_cidr = "your.ip.address/32"   # find with: curl -s ifconfig.me
```

### 3. Initialise and apply

```bash
export OP_SERVICE_ACCOUNT_TOKEN=$(op read "op://Private/Terraform SA/token")

just prod-tf-init
just prod-tf-plan    # review — no charges until apply
just prod-tf-apply
```

This creates: VPC, public subnet, security groups, EC2 (Ubuntu 24.04, Docker pre-installed), Elastic IP, S3 backup bucket, IAM instance profile.

### 4. Update 1Password with Terraform outputs

```bash
just prod-tf-outputs
# Copy `host_ip` → op://Production/App/production_host
# Copy `backup_bucket` → op://Production/App/backup_bucket
```

### 5. Bootstrap the application

```bash
just prod-bootstrap
# Pushes docker-stack.yml and .env.production (via op inject), initialises
# Docker Swarm, logs in to GHCR, and deploys the stack.

just prod-migrate latest   # run database migrations
```

---

## Routine deploys

After the GitHub Actions workflow pushes an image to GHCR:

```bash
just prod-deploy <sha>    # e.g. just prod-deploy abc1234
just prod-migrate <sha>   # if migrations are included in this release
```

Or let GitHub Actions handle it automatically on push to `main` (see `.github/workflows/deploy.yml`).

---

## Rollback

```bash
just prod-rollback         # reverts web + celery-worker to previous image
```

Docker Swarm retains the previous image on each node until a new deploy succeeds, so rollbacks are instant.

---

## Operations reference

```bash
just prod-status           # show all Swarm services and replica counts
just prod-logs             # tail web logs (default)
just prod-logs celery-worker
just prod-ssh              # interactive SSH session
just prod-backup           # trigger immediate PostgreSQL backup
```

---

## PostgreSQL backups

Backups run nightly at 02:00 AEST via cron on the manager node (configured in Terraform user_data):

```
0 2 * * * ubuntu docker service update --force app_pg-backup
```

The `pg-backup` service in `docker-stack.yml` runs `pg_dump | gzip | aws s3 cp` using the EC2 instance's IAM role — no AWS credentials needed in the environment.

Backups are retained for 30 days (configurable via `backup_retention_days` Terraform variable). An S3 lifecycle rule expires objects automatically.

### Restore procedure

```bash
# List available backups
aws s3 ls s3://$(just prod-tf-outputs | grep backup_bucket | awk '{print $3}')/postgres/

# Restore a specific backup (run on the production host or locally with VPN)
just prod-ssh
aws s3 cp s3://<backup-bucket>/postgres/<timestamp>.sql.gz - | \
    gunzip | \
    docker exec -i $(docker ps -qf name=app_db) \
        psql -U app app
```

Always test restores on staging before relying on production backups.

---

## Docker Swarm management

### Init (first-time, handled by `just prod-bootstrap`)

`just prod-bootstrap` runs `docker swarm init` automatically. To verify or re-initialise manually:

```bash
just prod-ssh

# Check if Swarm is already active
docker info --format '{{.Swarm.LocalNodeState}}'
# → "active" means Swarm is running; "inactive" means it needs initialising

# Initialise Swarm (only if inactive)
docker swarm init --advertise-addr <manager-ip>

# Verify manager status
docker node ls
```

### Add a worker node

On the manager node, get the join token:
```bash
docker swarm join-token worker
```

This prints a `docker swarm join` command. Run it on each new worker:
```bash
# On the worker node:
docker swarm join --token SWMTKN-<token> <manager-ip>:2377
```

Verify the worker appears:
```bash
docker node ls   # run on manager
```

After adding workers, update `docker-stack.yml` placement constraints as needed (e.g. remove `node.role == manager` constraints from stateless services) and redeploy:
```bash
just prod-deploy <current-sha>
```

---

## Scaling

To scale services without migrating to multi-node Swarm:

```bash
just prod-ssh
docker service scale app_web=3 app_celery-worker=3
```

---

## Secrets management summary

| Where | How |
|-------|-----|
| Terraform runs | `OP_SERVICE_ACCOUNT_TOKEN` env var + 1Password provider reads SSH public key |
| `.env.production` on host | `op inject -i deploy/.env.tpl` — resolved at push time, never stored in repo |
| GitHub Actions | `secrets.GITHUB_TOKEN` (auto), `secrets.PROD_SSH_KEY`, `secrets.PROD_HOST`, `secrets.PROD_USER` |
| EC2 → S3 backup | IAM instance profile — no credentials in environment |

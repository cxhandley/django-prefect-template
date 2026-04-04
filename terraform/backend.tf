terraform {
  backend "s3" {
    # Configured via: terraform init -backend-config=backend.hcl
    # Copy backend.hcl.example → backend.hcl (gitignored), fill in your bucket name, then run:
    #   just -f deploy/justfile tf-init
  }
}

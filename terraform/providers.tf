terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    onepassword = {
      source  = "1Password/1password"
      version = "~> 2.1"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "onepassword" {
  # Authenticates via OP_SERVICE_ACCOUNT_TOKEN env var.
  # Create a service account at: https://my.1password.com/developer-tools/service-accounts
  # Then: export OP_SERVICE_ACCOUNT_TOKEN=$(op read "op://Private/Terraform SA/token")
}

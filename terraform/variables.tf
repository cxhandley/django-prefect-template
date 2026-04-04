variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "ap-southeast-2"
}

variable "project" {
  description = "Short project name used to prefix resource names."
  type        = string
  default     = "app"
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
  default     = "production"
}

variable "instance_type" {
  description = "EC2 instance type for the Swarm manager / worker node."
  type        = string
  default     = "t3.medium"
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to reach port 22. Restrict to your static IP: \"1.2.3.4/32\"."
  type        = string
}

variable "backup_retention_days" {
  description = "Number of days to retain PostgreSQL backup objects in S3."
  type        = number
  default     = 30
}

variable "op_vault" {
  description = "Name of the 1Password vault that holds infrastructure secrets."
  type        = string
  default     = "Production"
}

variable "op_infra_item" {
  description = "Title of the 1Password item holding the SSH public key (field: public_key)."
  type        = string
  default     = "Infrastructure"
}

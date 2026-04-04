# ── 1Password: SSH public key ─────────────────────────────────────────────────

data "onepassword_item" "infra" {
  vault = var.op_vault
  title = var.op_infra_item
}

# ── AMI: latest Ubuntu 24.04 LTS ─────────────────────────────────────────────

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── VPC & Networking ──────────────────────────────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "${var.project}-${var.environment}"
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "${var.project}-${var.environment}"
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name        = "${var.project}-${var.environment}-public"
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name        = "${var.project}-${var.environment}-public"
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Security Groups ───────────────────────────────────────────────────────────

resource "aws_security_group" "web" {
  name        = "${var.project}-${var.environment}-web"
  description = "HTTP/HTTPS inbound from the internet"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project}-${var.environment}-web"
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_security_group" "ssh" {
  name        = "${var.project}-${var.environment}-ssh"
  description = "SSH inbound restricted to operator IP"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project}-${var.environment}-ssh"
    Project     = var.project
    Environment = var.environment
  }
}

# ── SSH Key Pair (public key sourced from 1Password) ─────────────────────────

resource "aws_key_pair" "deploy" {
  key_name   = "${var.project}-${var.environment}"
  public_key = data.onepassword_item.infra.fields["public_key"]

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ── IAM: EC2 instance profile for S3 backup writes ───────────────────────────

resource "aws_iam_role" "ec2" {
  name = "${var.project}-${var.environment}-ec2"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_iam_role_policy" "backup" {
  name = "${var.project}-${var.environment}-backup"
  role = aws_iam_role.ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject",
        ]
        Resource = [
          aws_s3_bucket.backup.arn,
          "${aws_s3_bucket.backup.arn}/*",
        ]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project}-${var.environment}-ec2"
  role = aws_iam_role.ec2.name
}

# ── EC2 Instance ──────────────────────────────────────────────────────────────

resource "aws_instance" "main" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  key_name               = aws_key_pair.deploy.key_name
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  vpc_security_group_ids = [aws_security_group.web.id, aws_security_group.ssh.id]

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 40
    delete_on_termination = true
    encrypted             = true
  }

  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail

    # Install Docker
    apt-get update -qq
    apt-get install -y --no-install-recommends ca-certificates curl gnupg

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

    # Allow ubuntu user to run Docker without sudo
    usermod -aG docker ubuntu

    # Install AWS CLI v2 (used by pg-backup service)
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    unzip -q /tmp/awscliv2.zip -d /tmp
    /tmp/aws/install
    rm -rf /tmp/awscliv2.zip /tmp/aws

    # Create app directory
    mkdir -p /opt/app
    chown ubuntu:ubuntu /opt/app

    # Schedule nightly PostgreSQL backup at 02:00
    echo "0 2 * * * ubuntu docker service update --force ${var.project}_pg-backup" \
        > /etc/cron.d/${var.project}-backup
  EOF

  tags = {
    Name        = "${var.project}-${var.environment}"
    Project     = var.project
    Environment = var.environment
  }

  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

# ── Elastic IP ────────────────────────────────────────────────────────────────

resource "aws_eip" "main" {
  instance = aws_instance.main.id
  domain   = "vpc"

  tags = {
    Name        = "${var.project}-${var.environment}"
    Project     = var.project
    Environment = var.environment
  }
}

# ── S3: PostgreSQL Backups ────────────────────────────────────────────────────

resource "aws_s3_bucket" "backup" {
  bucket = "${var.project}-${var.environment}-pg-backup-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name        = "${var.project}-${var.environment}-pg-backup"
    Project     = var.project
    Environment = var.environment
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    id     = "expire-old-backups"
    status = "Enabled"

    expiration {
      days = var.backup_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket = aws_s3_bucket.backup.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "host_ip" {
  description = "Elastic IP address of the production host."
  value       = aws_eip.main.public_ip
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.main.id
}

output "backup_bucket" {
  description = "Name of the S3 bucket used for PostgreSQL backups."
  value       = aws_s3_bucket.backup.bucket
}

output "ssh_command" {
  description = "Ready-to-use SSH command for the production host."
  value       = "ssh ubuntu@${aws_eip.main.public_ip}"
}

output "ami_id" {
  description = "AMI used for the EC2 instance."
  value       = data.aws_ami.ubuntu.id
}

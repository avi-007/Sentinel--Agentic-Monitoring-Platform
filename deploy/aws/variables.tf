variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type. t3.medium (2 vCPU / 4 GiB) is the minimum that comfortably runs Kafka+Zookeeper+Postgres+Grafana+3 services."
  type        = string
  default     = "t3.medium"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size. Holds Docker images plus Postgres data (named volume)."
  type        = number
  default     = 30
}

variable "key_name" {
  description = "Name of an existing EC2 key pair, for SSH access."
  type        = string
}

variable "ssh_cidr" {
  description = "CIDR allowed to SSH in, e.g. \"1.2.3.4/32\". Never leave this as 0.0.0.0/0."
  type        = string
}

variable "git_repo_url" {
  description = "Repo to clone on boot. Leave blank to upload the code yourself (e.g. rsync/scp) instead."
  type        = string
  default     = "https://github.com/avi-007/sentinel.git"
}

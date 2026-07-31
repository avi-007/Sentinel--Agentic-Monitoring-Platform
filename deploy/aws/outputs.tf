output "public_ip" {
  value = aws_eip.sentinel.public_ip
}

output "grafana_url" {
  value = "http://${aws_eip.sentinel.public_ip}:3000"
}

output "ssh_command" {
  value = "ssh ubuntu@${aws_eip.sentinel.public_ip}"
}

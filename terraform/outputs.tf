output "instance_id" {
  value       = aws_instance.n8n.id
  description = "EC2 instance ID (use with SSM start-session)"
}

output "public_ip" {
  value       = aws_instance.n8n.public_ip
  description = "Public IPv4 of the instance"
}

output "public_dns" {
  value       = aws_instance.n8n.public_dns
  description = "Public DNS name"
}

output "url" {
  value       = length(var.domain) > 0 ? "https://${var.domain}" : "http://${aws_instance.n8n.public_ip}"
  description = "Open this URL for n8n"
}

output "elastic_ip" {
  value       = aws_eip.n8n.public_ip
  description = "Static Elastic IP for DNS A record"
}

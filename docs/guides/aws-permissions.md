# AWS IAM Permissions Guide

This guide explains the AWS IAM permissions required to deploy n8n on EKS.

## Quick Start

### Option 1: Use Administrator Access (Simplest)
If your IAM user has `AdministratorAccess`, you're all set:

```bash
aws sts get-caller-identity --profile <your-profile>
# Should show your user ARN
```

### Option 2: Create Custom Policy (Recommended for Production)

Create a custom IAM policy with minimum required permissions:

## Required Permissions

### Core Services

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "eks:*",
        "iam:*",
        "elasticloadbalancing:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### Storage & Secrets

```json
{
  "Effect": "Allow",
  "Action": [
    "ssm:PutParameter",
    "ssm:GetParameter",
    "ssm:DeleteParameter",
    "ssm:DescribeParameters",
    "secretsmanager:CreateSecret",
    "secretsmanager:GetSecretValue",
    "secretsmanager:PutSecretValue",
    "secretsmanager:DeleteSecret",
    "secretsmanager:DescribeSecret",
    "secretsmanager:TagResource"
  ],
  "Resource": "*"
}
```

### Database (If using PostgreSQL)

```json
{
  "Effect": "Allow",
  "Action": [
    "rds:CreateDBInstance",
    "rds:DeleteDBInstance",
    "rds:DescribeDBInstances",
    "rds:CreateDBSubnetGroup",
    "rds:DeleteDBSubnetGroup",
    "rds:ModifyDBInstance",
    "rds:AddTagsToResource"
  ],
  "Resource": "*"
}
```

## Setup Instructions

### 1. Create IAM Policy

```bash
# Save the combined policy to aws-n8n-policy.json
cat > aws-n8n-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "eks:*",
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:PassRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:CreatePolicy",
        "iam:DeletePolicy",
        "iam:GetPolicy",
        "iam:TagRole",
        "iam:TagPolicy",
        "elasticloadbalancing:*",
        "ssm:PutParameter",
        "ssm:GetParameter",
        "ssm:DeleteParameter",
        "ssm:DescribeParameters",
        "secretsmanager:*",
        "rds:*"
      ],
      "Resource": "*"
    }
  ]
}
EOF

# Create the policy
aws iam create-policy \
  --policy-name N8N-EKS-Deployment \
  --policy-document file://aws-n8n-policy.json \
  --profile <your-profile>
```

### 2. Attach Policy to User

```bash
# Get your user ARN
USER_ARN=$(aws sts get-caller-identity --query Arn --output text --profile <your-profile>)
USER_NAME=$(echo $USER_ARN | cut -d'/' -f2)

# Get your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --profile <your-profile>)

# Attach the policy
aws iam attach-user-policy \
  --user-name $USER_NAME \
  --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/N8N-EKS-Deployment \
  --profile <your-profile>
```

### 3. Verify Permissions

```bash
# List attached policies
aws iam list-attached-user-policies \
  --user-name $USER_NAME \
  --profile <your-profile>

# Test access
aws sts get-caller-identity --profile <your-profile>
aws eks list-clusters --region us-east-1 --profile <your-profile>
```

## Common Permission Errors

### Error: "User is not authorized to perform: eks:CreateCluster"

**Solution**: Add EKS permissions to your IAM policy:
```bash
aws iam attach-user-policy \
  --user-name $USER_NAME \
  --policy-arn arn:aws:iam::aws:policy/AmazonEKSClusterPolicy \
  --profile <your-profile>
```

### Error: "User is not authorized to perform: iam:PassRole"

**Solution**: Ensure your policy includes `iam:PassRole`:
```json
{
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": "*"
}
```

### Error: "AccessDenied when calling the CreateSecurityGroup operation"

**Solution**: Add EC2 full access or specific VPC permissions:
```bash
aws iam attach-user-policy \
  --user-name $USER_NAME \
  --policy-arn arn:aws:iam::aws:policy/AmazonVPCFullAccess \
  --profile <your-profile>
```

## Service Limits

AWS has default service limits that may affect deployment:

### Check Current Limits

```bash
# EKS clusters per region
aws service-quotas get-service-quota \
  --service-code eks \
  --quota-code L-1194D53C \
  --region us-east-1 \
  --profile <your-profile>

# VPCs per region
aws service-quotas get-service-quota \
  --service-code vpc \
  --quota-code L-F678F1CE \
  --region us-east-1 \
  --profile <your-profile>

# Elastic IPs per region
aws service-quotas get-service-quota \
  --service-code ec2 \
  --quota-code L-0263D0A3 \
  --region us-east-1 \
  --profile <your-profile>
```

### Request Limit Increases

If you hit limits, request increases via AWS Service Quotas:
```bash
aws service-quotas request-service-quota-increase \
  --service-code eks \
  --quota-code L-1194D53C \
  --desired-value 10 \
  --region us-east-1 \
  --profile <your-profile>
```

## Troubleshooting

### Debug Permission Issues

```bash
# Simulate IAM policy
aws iam simulate-principal-policy \
  --policy-source-arn $USER_ARN \
  --action-names eks:CreateCluster ec2:CreateVpc \
  --profile <your-profile>

# View IAM user details
aws iam get-user --user-name $USER_NAME --profile <your-profile>

# List all policies
aws iam list-user-policies --user-name $USER_NAME --profile <your-profile>
aws iam list-attached-user-policies --user-name $USER_NAME --profile <your-profile>
```

### Enable CloudTrail for Audit

```bash
# Check recent IAM events
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=Username,AttributeValue=$USER_NAME \
  --max-results 10 \
  --profile <your-profile>
```

## Minimum Permissions Summary

For a minimal deployment (SQLite, no RDS), you need:

✅ **VPC & Networking**: Create VPC, subnets, NAT gateways, security groups
✅ **EKS**: Create cluster, node groups
✅ **IAM**: Create roles for EKS, attach policies
✅ **EC2**: Create load balancers, Elastic IPs
✅ **SSM**: Store encryption keys
✅ **Secrets Manager**: Store basic auth credentials

For PostgreSQL deployment, add:
✅ **RDS**: Create DB instances, subnet groups

## Security Best Practices

1. **Use Least Privilege**: Start with minimal permissions, add as needed
2. **Enable MFA**: Require multi-factor authentication for IAM users
3. **Use IAM Roles**: For EC2/Lambda access, use roles instead of access keys
4. **Rotate Credentials**: Regularly rotate access keys
5. **Monitor Access**: Enable CloudTrail and review logs

## Next Steps

- [AWS Deployment Guide](../deployment/aws.md)
- [Requirements](../reference/requirements.md)

## Support

- AWS IAM Documentation: https://docs.aws.amazon.com/IAM/
- GitHub Issues

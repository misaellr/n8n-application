# Configuration History Guide

## Overview

Every time you run `python setup.py`, your configuration choices are automatically saved in **two places**:

1. **`setup_history.log`** - Human-readable history of all setup runs (newest first)
2. **`.setup-current.json`** - Machine-readable current configuration (not committed to git)

This feature solves the problem you encountered: **"What parameters did I use last time?"**

## How It Works

### Automatic Saving

When you complete the configuration prompts in `setup.py`, your choices are automatically saved BEFORE applying them to Terraform:

```
python setup.py
→ Answer configuration questions
→ ✓ Configuration saved to setup_history.log
→ Applying Terraform...
```

### What Gets Saved

**Saved:**
- Cloud provider (AWS/Azure)
- All infrastructure parameters (cluster size, regions, etc.)
- Application settings (hostname, namespace, timezone, etc.)
- Database configuration
- Networking options (static IP, ingress, etc.)
- Timestamp of when you ran setup

**Redacted (for security):**
- Encryption keys (shown as `***REDACTED***`)
- Basic auth passwords (shown as `***REDACTED***`)

## The Two Files

### setup_history.log - Full History

This file contains **every setup.py run**, with the newest at the top.

**Format:**
```markdown
# Configuration - 2025-10-18 20:27:02

**Cloud Provider:** AZURE
**Timestamp:** 2025-10-18 20:27:02

## Configuration Parameters

### Cloud & Infrastructure
- **azure_subscription_id**: `013c5d82-8670-4c50-81d1-1c84a77a8303`
- **azure_location**: `eastus`
...

================================================================================

# Configuration - 2025-10-17 14:30:15
[previous run]
...
```

**Purpose:**
- See what changed between runs
- Compare different deployment configurations
- Audit trail of infrastructure changes
- Reference for "what did I use last time?"

**Committed to git:** ✅ Yes - Helps team members see configuration history (add to git manually if needed)

### .setup-current.json - Latest Configuration Only

This file contains ONLY the most recent configuration in JSON format.

**Format:**
```json
{
  "timestamp": "2025-10-18 20:27:02",
  "cloud_provider": "azure",
  "configuration": {
    "azure_subscription_id": "013c5d82-8670-4c50-81d1-1c84a77a8303",
    "cluster_name": "n8n-aks-cluster",
    ...
  }
}
```

**Purpose:**
- Quick reference for current deployed configuration
- Machine-readable for potential future features
- Easy to parse with scripts

**Committed to git:** ❌ No - In `.gitignore` (contains full config)

## Use Cases

### 1. Continuing After Failure

**Your situation:**
```bash
# First attempt failed due to permissions
python setup.py
# [answered all questions]
# [deployment failed]

# Now you need to retry - what were your answers?
# Just open setup_history.log and see the latest entry!
```

### 2. Comparing Configurations

```bash
# See what changed between deployments
diff terraform/azure/terraform.tfvars setup_history.log

# Or compare two different runs in setup_history.log
```

### 3. Team Collaboration

```bash
# Team member looks at git history
git log setup_history.log

# Sees:
# - Who ran setup and when
# - What parameters they used
# - What changed over time
```

### 4. Documentation

```bash
# Document your infrastructure setup
# The history file serves as automatic documentation
# of "how was this deployed?"
```

## Best Practices

### ✅ DO

- **Commit `setup_history.log` to git** - Team needs to see configuration history
- **Review the latest entry** before re-running setup.py with same parameters
- **Use it as a reference** when manually running Terraform
- **Check timestamps** to see when configuration last changed

### ❌ DON'T

- **Don't commit `.setup-current.json`** - Already in .gitignore
- **Don't manually edit setup_history.log** - It's auto-generated
- **Don't delete old entries** - History is valuable!
- **Don't store real secrets** - They're already redacted

## Example: Your Current Situation

**Problem:** Setup failed due to permissions. What parameters did you use?

**Solution:**
```bash
# Check the latest configuration
cat setup_history.log | head -50

# You'll see exactly:
# - Cluster name: n8n-aks-cluster
# - Location: eastus
# - Node count: 1
# - Static IP: False
# - Terraform manage role assignments: False
# etc.
```

**Now you can:**
1. Have admin grant permissions (see AZURE_MANUAL_PERMISSIONS.md)
2. Run `terraform apply` directly (uses existing tfvars)
3. OR run `python setup.py` again with exact same answers

## Advanced: Using .setup-current.json

Future enhancement ideas (not yet implemented):

```bash
# Load previous configuration
python setup.py --load-previous

# Compare with current terraform state
python scripts/compare_config.py
```

## File Locations

```
n8n-application/
├── setup_history.log          # Full configuration history (committed)
├── .setup-current.json        # Latest config only (gitignored)
├── terraform/
│   ├── aws/
│   │   └── terraform.tfvars   # Applied AWS configuration
│   └── azure/
│       └── terraform.tfvars   # Applied Azure configuration
```

## Summary

**setup_history.log answers:** "What parameters did I use when I ran setup?"
**terraform.tfvars answers:** "What is currently deployed?"

Both are useful, but setup_history.log is especially helpful when:
- Deployment failed and you need to retry with same parameters
- You want to see what changed over time
- Team members need to understand deployment decisions
- You're documenting your infrastructure

**The key benefit:** Never again wonder "what did I answer in setup.py?"

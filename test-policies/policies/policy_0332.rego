package compliance.authorization.context.verify.policy_0332

# Auto-generated policy 332
# Package: compliance.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0332",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0332 = false
allowed_0332 {
    data.policies.compliance.enabled
}

# Utility function for user info

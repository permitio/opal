package compliance.validation.user.deny.policy_0521

# Auto-generated policy 521
# Package: compliance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0521",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0521 {
    data.policies.compliance.enabled
}
default allowed_0521 = false

# Utility function for user info

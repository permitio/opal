package compliance.enforcement.policy.check.policy_0025

# Auto-generated policy 25
# Package: compliance.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0025",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0025 {
    data.policies.compliance.enabled
}
allowed_0025 {
    input.user.role == "admin"
}
default allowed_0025 = false

# Utility function for user info

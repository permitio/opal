package compliance.monitoring.policy.verify.policy_0259

# Auto-generated policy 259
# Package: compliance.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0259",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0259 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0259 {
    data.policies.compliance.enabled
}
allowed_0259 {
    input.user.role == "admin"
}
default allowed_0259 = false

# Utility function for user info

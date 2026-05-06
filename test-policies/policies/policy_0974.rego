package compliance.monitoring.user.allow.data.policy_0974

# Auto-generated policy 974
# Package: compliance.monitoring.user.allow.data

# Metadata
metadata := {
    "policy_id": "0974",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0974 {
    data.policies.compliance.enabled
}
denied_0974 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0974 {
    input.user.role == "admin"
}
default allowed_0974 = false

# Utility function for user info

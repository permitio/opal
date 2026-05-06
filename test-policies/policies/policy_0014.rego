package compliance.monitoring.action.allow.policy_0014

# Auto-generated policy 14
# Package: compliance.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0014",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0014 {
    input.user.role == "admin"
}
denied_0014 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

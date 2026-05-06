package compliance.authorization.action.allow.utils.policy_0381

# Auto-generated policy 381
# Package: compliance.authorization.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0381",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0381 {
    input.user.role == "admin"
}
denied_0381 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

package access.monitoring.user.allow.policy_0543

# Auto-generated policy 543
# Package: access.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0543",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0543 = false
denied_0543 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

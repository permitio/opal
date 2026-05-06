package audit.monitoring.user.allow.policy_0474

# Auto-generated policy 474
# Package: audit.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0474",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0474 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0474 {
    input.user.role == "admin"
}

# Utility function for user info

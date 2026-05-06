package compliance.monitoring.context.deny.utils.policy_0260

# Auto-generated policy 260
# Package: compliance.monitoring.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0260",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0260 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0260 {
    input.user.role == "admin"
}

# Utility function for user info

package risk.monitoring.context.deny.core.policy_0345

# Auto-generated policy 345
# Package: risk.monitoring.context.deny.core

# Metadata
metadata := {
    "policy_id": "0345",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0345 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0345 {
    data.policies.risk.enabled
}
default allowed_0345 = false

# Utility function for user info

package governance.monitoring.resource.deny.core.policy_0518

# Auto-generated policy 518
# Package: governance.monitoring.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0518",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0518 {
    input.user.role == "admin"
}
default allowed_0518 = false
denied_0518 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

package governance.monitoring.action.check.helpers.policy_0967

# Auto-generated policy 967
# Package: governance.monitoring.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0967",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0967 = false
allowed_0967 {
    input.user.role == "admin"
}
denied_0967 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

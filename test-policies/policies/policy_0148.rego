package compliance.monitoring.action.verify.helpers.policy_0148

# Auto-generated policy 148
# Package: compliance.monitoring.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0148",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0148 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0148 = false

# Utility function for user info

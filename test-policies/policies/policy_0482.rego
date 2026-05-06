package audit.authentication.action.check.utils.policy_0482

# Auto-generated policy 482
# Package: audit.authentication.action.check.utils

# Metadata
metadata := {
    "policy_id": "0482",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0482 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0482 = false

# Utility function for user info

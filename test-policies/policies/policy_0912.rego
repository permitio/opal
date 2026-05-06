package audit.authorization.action.deny.helpers.policy_0912

# Auto-generated policy 912
# Package: audit.authorization.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0912",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0912 = false
denied_0912 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

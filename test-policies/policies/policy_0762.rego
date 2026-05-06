package audit.authorization.context.allow.utils.policy_0762

# Auto-generated policy 762
# Package: audit.authorization.context.allow.utils

# Metadata
metadata := {
    "policy_id": "0762",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0762 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0762 = false

# Utility function for user info

package access.authorization.resource.allow.core.policy_0782

# Auto-generated policy 782
# Package: access.authorization.resource.allow.core

# Metadata
metadata := {
    "policy_id": "0782",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0782 = false
denied_0782 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

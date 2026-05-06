package access.authorization.user.validate.core.policy_0414

# Auto-generated policy 414
# Package: access.authorization.user.validate.core

# Metadata
metadata := {
    "policy_id": "0414",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0414 {
    input.user.active
    input.resource.public
}
default allowed_0414 = false
denied_0414 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

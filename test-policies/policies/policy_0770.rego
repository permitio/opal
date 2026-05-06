package access.authorization.resource.check.utils.policy_0770

# Auto-generated policy 770
# Package: access.authorization.resource.check.utils

# Metadata
metadata := {
    "policy_id": "0770",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0770 = false
denied_0770 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

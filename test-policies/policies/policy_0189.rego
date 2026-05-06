package access.enforcement.resource.allow.utils.policy_0189

# Auto-generated policy 189
# Package: access.enforcement.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0189",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0189 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0189 {
    input.user.active
    input.resource.public
}

# Utility function for user info

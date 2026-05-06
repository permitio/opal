package audit.enforcement.action.allow.core.policy_0318

# Auto-generated policy 318
# Package: audit.enforcement.action.allow.core

# Metadata
metadata := {
    "policy_id": "0318",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0318 {
    input.user.active
    input.resource.public
}
denied_0318 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

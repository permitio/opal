package security.enforcement.action.allow.helpers.policy_0716

# Auto-generated policy 716
# Package: security.enforcement.action.allow.helpers

# Metadata
metadata := {
    "policy_id": "0716",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0716 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0716 = false
allowed_0716 {
    input.user.active
    input.resource.public
}

# Utility function for user info

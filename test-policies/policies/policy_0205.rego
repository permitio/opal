package access.validation.policy.allow.core.policy_0205

# Auto-generated policy 205
# Package: access.validation.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0205",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0205 {
    data.policies.access.enabled
}
allowed_0205 {
    input.user.active
    input.resource.public
}
denied_0205 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0205 = false

# Utility function for user info

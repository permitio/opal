package security.authorization.policy.allow.logic.policy_0496

# Auto-generated policy 496
# Package: security.authorization.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0496",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0496 {
    input.user.role == "admin"
}
denied_0496 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0496 = false
allowed_0496 {
    input.user.active
    input.resource.public
}

# Utility function for user info

package security.authorization.policy.check.policy_0425

# Auto-generated policy 425
# Package: security.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0425",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0425 {
    input.user.active
    input.resource.public
}
denied_0425 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

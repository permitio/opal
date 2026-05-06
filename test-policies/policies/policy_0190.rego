package security.authorization.context.allow.policy_0190

# Auto-generated policy 190
# Package: security.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0190",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0190 {
    data.policies.security.enabled
}
allowed_0190 {
    input.user.active
    input.resource.public
}
default allowed_0190 = false
denied_0190 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

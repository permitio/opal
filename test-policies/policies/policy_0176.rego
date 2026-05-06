package security.authentication.user.validate.policy_0176

# Auto-generated policy 176
# Package: security.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0176",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0176 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0176 = false
allowed_0176 {
    input.user.active
    input.resource.public
}
allowed_0176 {
    data.policies.security.enabled
}

# Utility function for user info

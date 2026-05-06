package security.validation.resource.validate.policy_0978

# Auto-generated policy 978
# Package: security.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0978",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0978 {
    input.user.active
    input.resource.public
}
denied_0978 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0978 {
    data.policies.security.enabled
}

# Utility function for user info

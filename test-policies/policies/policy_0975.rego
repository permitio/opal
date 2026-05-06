package security.validation.resource.validate.policy_0975

# Auto-generated policy 975
# Package: security.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0975",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0975 = false
allowed_0975 {
    input.user.active
    input.resource.public
}
allowed_0975 {
    data.policies.security.enabled
}
allowed_0975 {
    input.user.role == "admin"
}

# Utility function for user info

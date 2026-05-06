package security.authorization.resource.check.data.policy_0194

# Auto-generated policy 194
# Package: security.authorization.resource.check.data

# Metadata
metadata := {
    "policy_id": "0194",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0194 {
    input.user.active
    input.resource.public
}
allowed_0194 {
    input.user.role == "admin"
}
allowed_0194 {
    data.policies.security.enabled
}
default allowed_0194 = false

# Utility function for user info

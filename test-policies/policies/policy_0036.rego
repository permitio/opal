package security.authorization.user.allow.utils.policy_0036

# Auto-generated policy 36
# Package: security.authorization.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0036",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0036 = false
allowed_0036 {
    input.user.active
    input.resource.public
}

# Utility function for user info

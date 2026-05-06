package security.authentication.policy.deny.policy_0073

# Auto-generated policy 73
# Package: security.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0073",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0073 {
    input.user.active
    input.resource.public
}
default allowed_0073 = false

# Utility function for user info

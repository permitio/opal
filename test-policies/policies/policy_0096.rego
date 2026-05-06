package security.authorization.user.deny.policy_0096

# Auto-generated policy 96
# Package: security.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0096",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0096 {
    input.user.active
    input.resource.public
}
default allowed_0096 = false

# Utility function for user info

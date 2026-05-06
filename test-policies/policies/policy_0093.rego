package governance.authorization.policy.allow.policy_0093

# Auto-generated policy 93
# Package: governance.authorization.policy.allow

# Metadata
metadata := {
    "policy_id": "0093",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0093 = false
allowed_0093 {
    input.user.active
    input.resource.public
}
allowed_0093 {
    input.user.role == "admin"
}

# Utility function for user info

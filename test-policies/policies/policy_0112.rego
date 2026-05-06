package access.authorization.action.allow.policy_0112

# Auto-generated policy 112
# Package: access.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0112",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0112 {
    data.policies.access.enabled
}
allowed_0112 {
    input.user.active
    input.resource.public
}

# Utility function for user info

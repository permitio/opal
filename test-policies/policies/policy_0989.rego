package access.authentication.action.check.data.policy_0989

# Auto-generated policy 989
# Package: access.authentication.action.check.data

# Metadata
metadata := {
    "policy_id": "0989",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0989 = false
allowed_0989 {
    data.policies.access.enabled
}
allowed_0989 {
    input.user.active
    input.resource.public
}

# Utility function for user info

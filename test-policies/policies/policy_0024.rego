package access.enforcement.action.deny.policy_0024

# Auto-generated policy 24
# Package: access.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0024",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0024 {
    input.user.active
    input.resource.public
}
allowed_0024 {
    data.policies.access.enabled
}
default allowed_0024 = false
allowed_0024 {
    input.user.role == "admin"
}

# Utility function for user info

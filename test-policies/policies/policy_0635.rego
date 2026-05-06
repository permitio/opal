package access.enforcement.resource.deny.utils.policy_0635

# Auto-generated policy 635
# Package: access.enforcement.resource.deny.utils

# Metadata
metadata := {
    "policy_id": "0635",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0635 {
    input.user.role == "admin"
}
allowed_0635 {
    data.policies.access.enabled
}
allowed_0635 {
    input.user.active
    input.resource.public
}

# Utility function for user info

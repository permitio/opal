package access.enforcement.resource.verify.policy_0086

# Auto-generated policy 86
# Package: access.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0086",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0086 {
    data.policies.access.enabled
}
allowed_0086 {
    input.user.role == "admin"
}
allowed_0086 {
    input.user.active
    input.resource.public
}

# Utility function for user info

package access.enforcement.context.validate.policy_0309

# Auto-generated policy 309
# Package: access.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0309",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0309 {
    input.user.role == "admin"
}
allowed_0309 {
    data.policies.access.enabled
}
allowed_0309 {
    input.user.active
    input.resource.public
}

# Utility function for user info

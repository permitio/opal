package access.enforcement.user.validate.policy_0239

# Auto-generated policy 239
# Package: access.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0239",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0239 {
    data.policies.access.enabled
}
allowed_0239 {
    input.user.active
    input.resource.public
}

# Utility function for user info

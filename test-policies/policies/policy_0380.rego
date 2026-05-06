package access.validation.policy.allow.policy_0380

# Auto-generated policy 380
# Package: access.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0380",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0380 {
    input.user.active
    input.resource.public
}
allowed_0380 {
    input.user.role == "admin"
}
allowed_0380 {
    data.policies.access.enabled
}

# Utility function for user info

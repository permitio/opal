package access.authentication.policy.validate.policy_0950

# Auto-generated policy 950
# Package: access.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0950",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0950 {
    input.user.active
    input.resource.public
}
allowed_0950 {
    data.policies.access.enabled
}

# Utility function for user info

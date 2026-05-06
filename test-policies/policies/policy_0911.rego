package access.monitoring.action.validate.policy_0911

# Auto-generated policy 911
# Package: access.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0911",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0911 {
    input.user.active
    input.resource.public
}
allowed_0911 {
    data.policies.access.enabled
}

# Utility function for user info

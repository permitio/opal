package access.monitoring.action.allow.policy_0607

# Auto-generated policy 607
# Package: access.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0607",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0607 {
    data.policies.access.enabled
}
allowed_0607 {
    input.user.active
    input.resource.public
}
allowed_0607 {
    input.user.role == "admin"
}

# Utility function for user info

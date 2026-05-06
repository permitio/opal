package access.monitoring.policy.deny.policy_0500

# Auto-generated policy 500
# Package: access.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0500",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0500 {
    data.policies.access.enabled
}
allowed_0500 {
    input.user.role == "admin"
}
allowed_0500 {
    input.user.active
    input.resource.public
}

# Utility function for user info

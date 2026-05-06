package audit.monitoring.policy.deny.policy_0034

# Auto-generated policy 34
# Package: audit.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0034",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0034 {
    input.user.active
    input.resource.public
}
allowed_0034 {
    data.policies.audit.enabled
}

# Utility function for user info

package access.monitoring.policy.validate.data.policy_0449

# Auto-generated policy 449
# Package: access.monitoring.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0449",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0449 = false
allowed_0449 {
    input.user.active
    input.resource.public
}
allowed_0449 {
    data.policies.access.enabled
}
allowed_0449 {
    input.user.role == "admin"
}

# Utility function for user info

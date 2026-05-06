package access.monitoring.user.validate.policy_0820

# Auto-generated policy 820
# Package: access.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0820",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0820 {
    data.policies.access.enabled
}
allowed_0820 {
    input.user.role == "admin"
}

# Utility function for user info

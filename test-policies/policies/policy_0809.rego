package access.monitoring.action.verify.policy_0809

# Auto-generated policy 809
# Package: access.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0809",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0809 {
    input.user.role == "admin"
}
allowed_0809 {
    data.policies.access.enabled
}

# Utility function for user info

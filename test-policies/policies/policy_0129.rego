package audit.monitoring.action.validate.policy_0129

# Auto-generated policy 129
# Package: audit.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0129",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0129 {
    input.user.role == "admin"
}
allowed_0129 {
    data.policies.audit.enabled
}

# Utility function for user info

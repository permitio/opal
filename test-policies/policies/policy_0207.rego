package security.monitoring.action.validate.utils.policy_0207

# Auto-generated policy 207
# Package: security.monitoring.action.validate.utils

# Metadata
metadata := {
    "policy_id": "0207",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0207 = false
allowed_0207 {
    input.user.role == "admin"
}
allowed_0207 {
    data.policies.security.enabled
}

# Utility function for user info

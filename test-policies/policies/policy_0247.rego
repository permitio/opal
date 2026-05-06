package security.monitoring.action.allow.policy_0247

# Auto-generated policy 247
# Package: security.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0247",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0247 {
    data.policies.security.enabled
}
allowed_0247 {
    input.user.active
    input.resource.public
}
default allowed_0247 = false

# Utility function for user info

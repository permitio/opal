package security.monitoring.resource.allow.policy_0059

# Auto-generated policy 59
# Package: security.monitoring.resource.allow

# Metadata
metadata := {
    "policy_id": "0059",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0059 = false
allowed_0059 {
    data.policies.security.enabled
}
allowed_0059 {
    input.user.role == "admin"
}
approved_0059 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

package security.monitoring.context.allow.utils.policy_0996

# Auto-generated policy 996
# Package: security.monitoring.context.allow.utils

# Metadata
metadata := {
    "policy_id": "0996",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0996 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0996 {
    data.policies.security.enabled
}
allowed_0996 {
    input.user.active
    input.resource.public
}
approved_0996 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

package access.monitoring.action.allow.data.policy_0569

# Auto-generated policy 569
# Package: access.monitoring.action.allow.data

# Metadata
metadata := {
    "policy_id": "0569",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0569 {
    data.policies.access.enabled
}
approved_0569 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

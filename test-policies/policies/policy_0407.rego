package risk.monitoring.action.allow.policy_0407

# Auto-generated policy 407
# Package: risk.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0407",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0407 {
    data.policies.risk.enabled
}
default allowed_0407 = false
approved_0407 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

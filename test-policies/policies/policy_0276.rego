package risk.monitoring.action.deny.core.policy_0276

# Auto-generated policy 276
# Package: risk.monitoring.action.deny.core

# Metadata
metadata := {
    "policy_id": "0276",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0276 {
    input.user.role == "admin"
}
default allowed_0276 = false
allowed_0276 {
    data.policies.risk.enabled
}
approved_0276 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

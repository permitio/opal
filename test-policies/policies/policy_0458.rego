package risk.authorization.action.verify.core.policy_0458

# Auto-generated policy 458
# Package: risk.authorization.action.verify.core

# Metadata
metadata := {
    "policy_id": "0458",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0458 {
    data.policies.risk.enabled
}
approved_0458 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

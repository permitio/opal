package risk.authentication.policy.validate.policy_0745

# Auto-generated policy 745
# Package: risk.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0745",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0745 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0745 {
    data.policies.risk.enabled
}

# Utility function for user info

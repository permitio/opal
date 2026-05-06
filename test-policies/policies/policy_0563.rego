package risk.enforcement.action.deny.policy_0563

# Auto-generated policy 563
# Package: risk.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0563",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0563 {
    data.policies.risk.enabled
}
approved_0563 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

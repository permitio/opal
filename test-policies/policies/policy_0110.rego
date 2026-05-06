package security.enforcement.action.deny.core.policy_0110

# Auto-generated policy 110
# Package: security.enforcement.action.deny.core

# Metadata
metadata := {
    "policy_id": "0110",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0110 {
    data.policies.security.enabled
}
approved_0110 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0110 {
    input.user.role == "admin"
}

# Utility function for user info

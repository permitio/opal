package audit.authorization.action.deny.data.policy_0130

# Auto-generated policy 130
# Package: audit.authorization.action.deny.data

# Metadata
metadata := {
    "policy_id": "0130",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0130 {
    data.policies.audit.enabled
}
allowed_0130 {
    input.user.role == "admin"
}
approved_0130 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

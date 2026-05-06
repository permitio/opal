package audit.authorization.user.allow.policy_0175

# Auto-generated policy 175
# Package: audit.authorization.user.allow

# Metadata
metadata := {
    "policy_id": "0175",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0175 {
    input.user.role == "admin"
}
approved_0175 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0175 {
    data.policies.audit.enabled
}

# Utility function for user info

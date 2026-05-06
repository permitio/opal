package audit.authorization.policy.validate.logic.policy_0117

# Auto-generated policy 117
# Package: audit.authorization.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0117",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0117 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0117 {
    data.policies.audit.enabled
}

# Utility function for user info

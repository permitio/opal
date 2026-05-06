package risk.validation.policy.validate.policy_0384

# Auto-generated policy 384
# Package: risk.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0384",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0384 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0384 {
    input.user.role == "admin"
}
default allowed_0384 = false
allowed_0384 {
    data.policies.risk.enabled
}

# Utility function for user info

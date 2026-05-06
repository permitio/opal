package security.authentication.action.validate.utils.policy_0335

# Auto-generated policy 335
# Package: security.authentication.action.validate.utils

# Metadata
metadata := {
    "policy_id": "0335",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0335 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0335 {
    data.policies.security.enabled
}

# Utility function for user info

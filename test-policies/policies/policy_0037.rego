package governance.validation.user.allow.helpers.policy_0037

# Auto-generated policy 37
# Package: governance.validation.user.allow.helpers

# Metadata
metadata := {
    "policy_id": "0037",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0037 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0037 {
    data.policies.governance.enabled
}

# Utility function for user info

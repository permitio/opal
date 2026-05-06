package governance.authentication.context.validate.utils.policy_0237

# Auto-generated policy 237
# Package: governance.authentication.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0237",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0237 = false
approved_0237 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0237 {
    data.policies.governance.enabled
}

# Utility function for user info

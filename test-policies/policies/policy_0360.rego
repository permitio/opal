package governance.validation.resource.validate.policy_0360

# Auto-generated policy 360
# Package: governance.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0360",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0360 = false
allowed_0360 {
    data.policies.governance.enabled
}
approved_0360 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

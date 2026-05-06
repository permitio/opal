package security.validation.policy.validate.policy_0409

# Auto-generated policy 409
# Package: security.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0409",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0409 = false
approved_0409 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0409 {
    data.policies.security.enabled
}
allowed_0409 {
    input.user.active
    input.resource.public
}

# Utility function for user info

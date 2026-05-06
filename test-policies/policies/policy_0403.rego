package risk.validation.policy.deny.data.policy_0403

# Auto-generated policy 403
# Package: risk.validation.policy.deny.data

# Metadata
metadata := {
    "policy_id": "0403",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0403 {
    data.policies.risk.enabled
}
approved_0403 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0403 {
    input.user.active
    input.resource.public
}

# Utility function for user info

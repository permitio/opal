package risk.authorization.user.validate.policy_0560

# Auto-generated policy 560
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0560",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0560 {
    data.policies.risk.enabled
}
allowed_0560 {
    input.user.active
    input.resource.public
}
approved_0560 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

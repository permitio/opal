package risk.authentication.resource.validate.policy_0262

# Auto-generated policy 262
# Package: risk.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0262",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0262 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0262 {
    data.policies.risk.enabled
}

# Utility function for user info

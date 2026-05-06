package risk.authorization.context.allow.policy_0880

# Auto-generated policy 880
# Package: risk.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0880",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0880 {
    input.user.active
    input.resource.public
}
allowed_0880 {
    data.policies.risk.enabled
}
default allowed_0880 = false
approved_0880 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

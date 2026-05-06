package risk.authorization.resource.allow.policy_0415

# Auto-generated policy 415
# Package: risk.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0415",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0415 = false
allowed_0415 {
    input.user.active
    input.resource.public
}
allowed_0415 {
    data.policies.risk.enabled
}
approved_0415 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

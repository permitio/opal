package risk.authorization.user.validate.policy_0643

# Auto-generated policy 643
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0643",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0643 {
    data.policies.risk.enabled
}
default allowed_0643 = false
allowed_0643 {
    input.user.active
    input.resource.public
}
approved_0643 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

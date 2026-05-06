package audit.authorization.policy.validate.policy_0372

# Auto-generated policy 372
# Package: audit.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0372",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0372 {
    input.user.active
    input.resource.public
}
approved_0372 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

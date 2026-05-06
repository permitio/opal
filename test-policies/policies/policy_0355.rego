package security.authorization.policy.validate.policy_0355

# Auto-generated policy 355
# Package: security.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0355",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0355 = false
allowed_0355 {
    input.user.role == "admin"
}
allowed_0355 {
    input.user.active
    input.resource.public
}
approved_0355 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

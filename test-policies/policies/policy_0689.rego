package risk.authorization.context.validate.policy_0689

# Auto-generated policy 689
# Package: risk.authorization.context.validate

# Metadata
metadata := {
    "policy_id": "0689",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0689 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0689 {
    data.policies.risk.enabled
}
allowed_0689 {
    input.user.role == "admin"
}
allowed_0689 {
    input.user.active
    input.resource.public
}

# Utility function for user info

package governance.authorization.policy.validate.policy_0181

# Auto-generated policy 181
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0181",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0181 = false
approved_0181 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0181 {
    input.user.role == "admin"
}
allowed_0181 {
    input.user.active
    input.resource.public
}

# Utility function for user info

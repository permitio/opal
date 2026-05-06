package governance.authorization.user.validate.policy_0835

# Auto-generated policy 835
# Package: governance.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0835",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0835 = false
approved_0835 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0835 {
    input.user.active
    input.resource.public
}

# Utility function for user info

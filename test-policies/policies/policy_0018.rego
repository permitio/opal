package governance.authorization.context.validate.policy_0018

# Auto-generated policy 18
# Package: governance.authorization.context.validate

# Metadata
metadata := {
    "policy_id": "0018",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0018 {
    input.user.active
    input.resource.public
}
approved_0018 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

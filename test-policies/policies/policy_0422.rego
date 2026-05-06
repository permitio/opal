package governance.authorization.policy.validate.logic.policy_0422

# Auto-generated policy 422
# Package: governance.authorization.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0422",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0422 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0422 {
    input.user.active
    input.resource.public
}

# Utility function for user info

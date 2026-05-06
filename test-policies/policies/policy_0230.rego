package governance.authorization.policy.validate.policy_0230

# Auto-generated policy 230
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0230",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0230 {
    data.policies.governance.enabled
}
approved_0230 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0230 {
    input.user.active
    input.resource.public
}

# Utility function for user info

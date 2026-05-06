package governance.authorization.context.check.policy_0944

# Auto-generated policy 944
# Package: governance.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0944",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0944 {
    data.policies.governance.enabled
}
approved_0944 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0944 {
    input.user.active
    input.resource.public
}

# Utility function for user info

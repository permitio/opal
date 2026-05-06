package audit.authorization.policy.validate.policy_0725

# Auto-generated policy 725
# Package: audit.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0725",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0725 {
    input.user.active
    input.resource.public
}
approved_0725 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0725 {
    data.policies.audit.enabled
}

# Utility function for user info

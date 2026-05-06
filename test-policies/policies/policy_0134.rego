package audit.authorization.policy.deny.policy_0134

# Auto-generated policy 134
# Package: audit.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0134",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0134 {
    input.user.active
    input.resource.public
}
approved_0134 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0134 {
    data.policies.audit.enabled
}

# Utility function for user info

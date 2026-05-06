package access.authorization.policy.deny.policy_0636

# Auto-generated policy 636
# Package: access.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0636",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0636 {
    input.user.role == "admin"
}
approved_0636 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0636 {
    data.policies.access.enabled
}

# Utility function for user info

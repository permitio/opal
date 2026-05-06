package risk.authorization.policy.validate.policy_0065

# Auto-generated policy 65
# Package: risk.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0065",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0065 {
    input.user.active
    input.resource.public
}
approved_0065 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0065 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0065 {
    data.policies.risk.enabled
}

# Utility function for user info

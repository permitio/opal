package risk.authorization.action.allow.policy_0006

# Auto-generated policy 6
# Package: risk.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0006",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0006 {
    input.user.active
    input.resource.public
}
allowed_0006 {
    data.policies.risk.enabled
}
denied_0006 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0006 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

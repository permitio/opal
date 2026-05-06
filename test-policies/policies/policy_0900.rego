package risk.authorization.action.allow.utils.policy_0900

# Auto-generated policy 900
# Package: risk.authorization.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0900",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0900 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0900 {
    input.user.active
    input.resource.public
}

# Utility function for user info

package compliance.authorization.policy.deny.core.policy_0953

# Auto-generated policy 953
# Package: compliance.authorization.policy.deny.core

# Metadata
metadata := {
    "policy_id": "0953",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0953 {
    input.user.active
    input.resource.public
}
approved_0953 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0953 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

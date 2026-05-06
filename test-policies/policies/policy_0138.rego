package access.monitoring.context.deny.logic.policy_0138

# Auto-generated policy 138
# Package: access.monitoring.context.deny.logic

# Metadata
metadata := {
    "policy_id": "0138",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0138 {
    input.user.active
    input.resource.public
}
approved_0138 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

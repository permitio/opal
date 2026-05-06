package access.monitoring.action.allow.logic.policy_0517

# Auto-generated policy 517
# Package: access.monitoring.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0517",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0517 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0517 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0517 {
    input.user.active
    input.resource.public
}
default allowed_0517 = false

# Utility function for user info

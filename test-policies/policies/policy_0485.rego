package access.monitoring.resource.allow.utils.policy_0485

# Auto-generated policy 485
# Package: access.monitoring.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0485",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0485 {
    input.user.role == "admin"
}
allowed_0485 {
    input.user.active
    input.resource.public
}
approved_0485 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0485 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

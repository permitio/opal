package compliance.monitoring.resource.allow.utils.policy_0339

# Auto-generated policy 339
# Package: compliance.monitoring.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0339",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0339 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0339 {
    input.user.active
    input.resource.public
}
default allowed_0339 = false
approved_0339 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

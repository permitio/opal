package audit.monitoring.context.allow.logic.policy_0350

# Auto-generated policy 350
# Package: audit.monitoring.context.allow.logic

# Metadata
metadata := {
    "policy_id": "0350",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0350 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0350 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0350 = false
allowed_0350 {
    input.user.role == "admin"
}

# Utility function for user info

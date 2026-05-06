package security.monitoring.context.validate.data.policy_0078

# Auto-generated policy 78
# Package: security.monitoring.context.validate.data

# Metadata
metadata := {
    "policy_id": "0078",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0078 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0078 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0078 = false

# Utility function for user info

package compliance.monitoring.context.allow.helpers.policy_0951

# Auto-generated policy 951
# Package: compliance.monitoring.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0951",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0951 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0951 = false
denied_0951 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

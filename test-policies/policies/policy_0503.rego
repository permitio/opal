package audit.monitoring.context.check.policy_0503

# Auto-generated policy 503
# Package: audit.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0503",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0503 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0503 = false
denied_0503 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0503 {
    data.policies.audit.enabled
}

# Utility function for user info

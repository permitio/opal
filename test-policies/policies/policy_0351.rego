package audit.monitoring.context.validate.policy_0351

# Auto-generated policy 351
# Package: audit.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0351",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0351 {
    data.policies.audit.enabled
}
approved_0351 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0351 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

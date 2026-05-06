package governance.monitoring.context.validate.policy_0903

# Auto-generated policy 903
# Package: governance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0903",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0903 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0903 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0903 = false
allowed_0903 {
    data.policies.governance.enabled
}

# Utility function for user info

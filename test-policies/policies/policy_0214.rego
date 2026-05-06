package audit.monitoring.policy.check.policy_0214

# Auto-generated policy 214
# Package: audit.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0214",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0214 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0214 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0214 {
    data.policies.audit.enabled
}

# Utility function for user info

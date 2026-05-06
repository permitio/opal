package audit.monitoring.resource.validate.policy_0447

# Auto-generated policy 447
# Package: audit.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0447",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0447 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0447 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0447 {
    data.policies.audit.enabled
}

# Utility function for user info

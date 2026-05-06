package risk.monitoring.action.validate.policy_0683

# Auto-generated policy 683
# Package: risk.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0683",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0683 = false
denied_0683 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0683 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0683 {
    data.policies.risk.enabled
}

# Utility function for user info

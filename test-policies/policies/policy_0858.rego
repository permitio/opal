package compliance.monitoring.policy.check.helpers.policy_0858

# Auto-generated policy 858
# Package: compliance.monitoring.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0858",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0858 = false
approved_0858 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0858 {
    input.user.active
    input.resource.public
}
denied_0858 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

package audit.monitoring.context.check.data.policy_0803

# Auto-generated policy 803
# Package: audit.monitoring.context.check.data

# Metadata
metadata := {
    "policy_id": "0803",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0803 = false
approved_0803 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

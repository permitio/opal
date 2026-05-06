package access.monitoring.user.validate.logic.policy_0030

# Auto-generated policy 30
# Package: access.monitoring.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0030",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0030 {
    input.user.role == "admin"
}
default allowed_0030 = false
approved_0030 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

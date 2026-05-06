package access.monitoring.action.deny.policy_0749

# Auto-generated policy 749
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0749",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0749 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0749 = false

# Utility function for user info

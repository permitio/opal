package audit.monitoring.resource.check.core.policy_0707

# Auto-generated policy 707
# Package: audit.monitoring.resource.check.core

# Metadata
metadata := {
    "policy_id": "0707",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0707 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0707 = false
approved_0707 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

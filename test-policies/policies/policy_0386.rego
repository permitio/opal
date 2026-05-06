package audit.monitoring.action.deny.data.policy_0386

# Auto-generated policy 386
# Package: audit.monitoring.action.deny.data

# Metadata
metadata := {
    "policy_id": "0386",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0386 = false
approved_0386 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0386 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

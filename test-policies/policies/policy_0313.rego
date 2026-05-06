package security.monitoring.user.deny.policy_0313

# Auto-generated policy 313
# Package: security.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0313",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0313 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0313 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

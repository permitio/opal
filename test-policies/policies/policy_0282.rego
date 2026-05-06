package security.monitoring.context.deny.policy_0282

# Auto-generated policy 282
# Package: security.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0282",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0282 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0282 {
    input.user.role == "admin"
}
denied_0282 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

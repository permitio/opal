package risk.monitoring.user.check.policy_0406

# Auto-generated policy 406
# Package: risk.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0406",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0406 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0406 = false
approved_0406 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0406 {
    input.user.role == "admin"
}

# Utility function for user info

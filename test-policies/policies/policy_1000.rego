package audit.monitoring.action.deny.policy_1000

# Auto-generated policy 1000
# Package: audit.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "1000",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_1000 {
    input.user.role == "admin"
}
approved_1000 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_1000 {
    input.user.active
    input.resource.public
}
denied_1000 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

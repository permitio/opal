package audit.monitoring.action.check.policy_0187

# Auto-generated policy 187
# Package: audit.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0187",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0187 {
    input.user.role == "admin"
}
approved_0187 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0187 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0187 = false

# Utility function for user info

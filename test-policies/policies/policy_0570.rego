package access.enforcement.action.check.data.policy_0570

# Auto-generated policy 570
# Package: access.enforcement.action.check.data

# Metadata
metadata := {
    "policy_id": "0570",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0570 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0570 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0570 = false

# Utility function for user info

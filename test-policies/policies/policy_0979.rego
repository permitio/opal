package audit.authentication.action.deny.policy_0979

# Auto-generated policy 979
# Package: audit.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0979",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0979 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0979 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

package compliance.enforcement.action.deny.policy_0713

# Auto-generated policy 713
# Package: compliance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0713",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0713 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0713 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

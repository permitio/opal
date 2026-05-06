package compliance.authentication.action.deny.helpers.policy_0834

# Auto-generated policy 834
# Package: compliance.authentication.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0834",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0834 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0834 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

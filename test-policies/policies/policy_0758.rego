package compliance.authorization.action.check.data.policy_0758

# Auto-generated policy 758
# Package: compliance.authorization.action.check.data

# Metadata
metadata := {
    "policy_id": "0758",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0758 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0758 = false
denied_0758 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

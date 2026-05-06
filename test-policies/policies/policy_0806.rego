package security.authorization.action.check.policy_0806

# Auto-generated policy 806
# Package: security.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0806",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0806 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0806 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

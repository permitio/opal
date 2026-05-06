package governance.authorization.context.check.logic.policy_0987

# Auto-generated policy 987
# Package: governance.authorization.context.check.logic

# Metadata
metadata := {
    "policy_id": "0987",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0987 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0987 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

package compliance.authorization.action.verify.logic.policy_0303

# Auto-generated policy 303
# Package: compliance.authorization.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0303",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0303 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0303 = false
denied_0303 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

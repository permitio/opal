package governance.authentication.action.check.policy_0008

# Auto-generated policy 8
# Package: governance.authentication.action.check

# Metadata
metadata := {
    "policy_id": "0008",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0008 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0008 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

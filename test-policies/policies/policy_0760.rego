package governance.authentication.action.verify.utils.policy_0760

# Auto-generated policy 760
# Package: governance.authentication.action.verify.utils

# Metadata
metadata := {
    "policy_id": "0760",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0760 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0760 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

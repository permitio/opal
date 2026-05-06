package governance.authorization.context.deny.utils.policy_0013

# Auto-generated policy 13
# Package: governance.authorization.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0013",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0013 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0013 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0013 {
    data.policies.governance.enabled
}

# Utility function for user info

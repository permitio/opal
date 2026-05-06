package governance.authorization.policy.verify.policy_0121

# Auto-generated policy 121
# Package: governance.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0121",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0121 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0121 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0121 {
    data.policies.governance.enabled
}

# Utility function for user info

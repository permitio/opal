package governance.enforcement.policy.allow.logic.policy_0128

# Auto-generated policy 128
# Package: governance.enforcement.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0128",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0128 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0128 = false
allowed_0128 {
    data.policies.governance.enabled
}
denied_0128 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

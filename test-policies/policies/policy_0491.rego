package governance.enforcement.policy.allow.policy_0491

# Auto-generated policy 491
# Package: governance.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0491",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0491 {
    data.policies.governance.enabled
}
default allowed_0491 = false
allowed_0491 {
    input.user.role == "admin"
}
approved_0491 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

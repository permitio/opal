package risk.enforcement.policy.allow.policy_0954

# Auto-generated policy 954
# Package: risk.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0954",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0954 {
    data.policies.risk.enabled
}
approved_0954 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0954 = false

# Utility function for user info

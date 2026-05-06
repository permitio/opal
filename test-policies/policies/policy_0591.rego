package access.enforcement.user.deny.policy_0591

# Auto-generated policy 591
# Package: access.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0591",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0591 {
    data.policies.access.enabled
}
approved_0591 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0591 = false

# Utility function for user info

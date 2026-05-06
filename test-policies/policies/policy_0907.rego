package compliance.enforcement.policy.verify.utils.policy_0907

# Auto-generated policy 907
# Package: compliance.enforcement.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0907",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0907 = false
approved_0907 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0907 {
    data.policies.compliance.enabled
}

# Utility function for user info

package governance.authentication.policy.check.core.policy_0264

# Auto-generated policy 264
# Package: governance.authentication.policy.check.core

# Metadata
metadata := {
    "policy_id": "0264",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0264 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0264 {
    data.policies.governance.enabled
}
allowed_0264 {
    input.user.role == "admin"
}

# Utility function for user info

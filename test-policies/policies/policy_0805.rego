package governance.enforcement.policy.validate.policy_0805

# Auto-generated policy 805
# Package: governance.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0805",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0805 {
    input.user.role == "admin"
}
approved_0805 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0805 {
    data.policies.governance.enabled
}

# Utility function for user info

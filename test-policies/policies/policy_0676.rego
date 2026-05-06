package security.enforcement.policy.validate.policy_0676

# Auto-generated policy 676
# Package: security.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0676",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0676 {
    input.user.role == "admin"
}
approved_0676 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0676 {
    data.policies.security.enabled
}
default allowed_0676 = false

# Utility function for user info

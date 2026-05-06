package security.enforcement.policy.validate.policy_0290

# Auto-generated policy 290
# Package: security.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0290",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0290 {
    data.policies.security.enabled
}
default allowed_0290 = false
approved_0290 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0290 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

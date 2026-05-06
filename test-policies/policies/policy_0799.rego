package security.validation.action.allow.helpers.policy_0799

# Auto-generated policy 799
# Package: security.validation.action.allow.helpers

# Metadata
metadata := {
    "policy_id": "0799",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0799 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0799 {
    data.policies.security.enabled
}
approved_0799 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0799 = false

# Utility function for user info

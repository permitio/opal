package security.validation.action.deny.policy_0802

# Auto-generated policy 802
# Package: security.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0802",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0802 {
    data.policies.security.enabled
}
default allowed_0802 = false
approved_0802 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0802 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

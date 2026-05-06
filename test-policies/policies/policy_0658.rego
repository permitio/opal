package security.enforcement.resource.allow.utils.policy_0658

# Auto-generated policy 658
# Package: security.enforcement.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0658",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0658 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0658 = false
allowed_0658 {
    data.policies.security.enabled
}
denied_0658 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

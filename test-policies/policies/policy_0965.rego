package access.validation.user.allow.utils.policy_0965

# Auto-generated policy 965
# Package: access.validation.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0965",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0965 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
denied_0965 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0965 {
    data.policies.access.enabled
}
default allowed_0965 = false

# Utility function for user info

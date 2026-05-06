package security.authentication.action.validate.utils.policy_0970

# Auto-generated policy 970
# Package: security.authentication.action.validate.utils

# Metadata
metadata := {
    "policy_id": "0970",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0970 {
    data.policies.security.enabled
}
denied_0970 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0970 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

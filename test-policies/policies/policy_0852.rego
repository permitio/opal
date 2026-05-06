package security.authorization.action.allow.utils.policy_0852

# Auto-generated policy 852
# Package: security.authorization.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0852",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0852 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0852 {
    data.policies.security.enabled
}
allowed_0852 {
    input.user.role == "admin"
}
approved_0852 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info

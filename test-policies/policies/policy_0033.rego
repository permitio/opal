package security.authorization.policy.allow.logic.policy_0033

# Auto-generated policy 33
# Package: security.authorization.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0033",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0033 {
    data.policies.security.enabled
}
allowed_0033 {
    input.user.role == "admin"
}

# Utility function for user info

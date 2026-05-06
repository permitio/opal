package security.authorization.action.check.policy_0346

# Auto-generated policy 346
# Package: security.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0346",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0346 {
    data.policies.security.enabled
}
denied_0346 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

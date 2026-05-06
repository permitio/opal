package security.authentication.action.verify.policy_0312

# Auto-generated policy 312
# Package: security.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0312",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0312 {
    input.user.role == "admin"
}
allowed_0312 {
    data.policies.security.enabled
}
denied_0312 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

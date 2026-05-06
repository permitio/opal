package access.authentication.policy.check.policy_0257

# Auto-generated policy 257
# Package: access.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0257",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0257 {
    data.policies.access.enabled
}
denied_0257 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

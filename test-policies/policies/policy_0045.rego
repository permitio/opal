package audit.authentication.policy.verify.core.policy_0045

# Auto-generated policy 45
# Package: audit.authentication.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0045",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0045 {
    input.user.role == "admin"
}
allowed_0045 {
    data.policies.audit.enabled
}
default allowed_0045 = false
denied_0045 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

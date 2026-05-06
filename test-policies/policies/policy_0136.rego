package audit.validation.user.allow.policy_0136

# Auto-generated policy 136
# Package: audit.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0136",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0136 {
    data.policies.audit.enabled
}
denied_0136 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

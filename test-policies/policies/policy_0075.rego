package audit.enforcement.action.verify.core.policy_0075

# Auto-generated policy 75
# Package: audit.enforcement.action.verify.core

# Metadata
metadata := {
    "policy_id": "0075",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0075 {
    data.policies.audit.enabled
}
allowed_0075 {
    input.user.role == "admin"
}

# Utility function for user info

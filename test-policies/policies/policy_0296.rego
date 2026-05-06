package governance.validation.action.allow.policy_0296

# Auto-generated policy 296
# Package: governance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0296",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0296 {
    input.user.role == "admin"
}
allowed_0296 {
    data.policies.governance.enabled
}

# Utility function for user info

package security.validation.action.verify.helpers.policy_0640

# Auto-generated policy 640
# Package: security.validation.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0640",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0640 {
    data.policies.security.enabled
}
denied_0640 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

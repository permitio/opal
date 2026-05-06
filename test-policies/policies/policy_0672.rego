package audit.enforcement.action.validate.helpers.policy_0672

# Auto-generated policy 672
# Package: audit.enforcement.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0672",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0672 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0672 {
    data.policies.audit.enabled
}

# Utility function for user info

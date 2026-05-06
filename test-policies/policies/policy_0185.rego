package audit.validation.action.verify.helpers.policy_0185

# Auto-generated policy 185
# Package: audit.validation.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0185",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0185 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0185 = false
allowed_0185 {
    data.policies.audit.enabled
}

# Utility function for user info

package audit.validation.context.check.policy_0717

# Auto-generated policy 717
# Package: audit.validation.context.check

# Metadata
metadata := {
    "policy_id": "0717",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0717 = false
denied_0717 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0717 {
    data.policies.audit.enabled
}

# Utility function for user info

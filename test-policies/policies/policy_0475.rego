package compliance.validation.context.validate.logic.policy_0475

# Auto-generated policy 475
# Package: compliance.validation.context.validate.logic

# Metadata
metadata := {
    "policy_id": "0475",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0475 {
    data.policies.compliance.enabled
}
default allowed_0475 = false
denied_0475 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

package audit.authentication.action.validate.policy_0330

# Auto-generated policy 330
# Package: audit.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0330",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0330 {
    data.policies.audit.enabled
}
allowed_0330 {
    input.user.active
    input.resource.public
}

# Utility function for user info

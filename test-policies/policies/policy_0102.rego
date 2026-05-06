package access.authentication.action.validate.logic.policy_0102

# Auto-generated policy 102
# Package: access.authentication.action.validate.logic

# Metadata
metadata := {
    "policy_id": "0102",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0102 = false
allowed_0102 {
    input.user.role == "admin"
}
allowed_0102 {
    input.user.active
    input.resource.public
}
allowed_0102 {
    data.policies.access.enabled
}

# Utility function for user info

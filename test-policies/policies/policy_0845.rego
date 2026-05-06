package access.authentication.policy.validate.policy_0845

# Auto-generated policy 845
# Package: access.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0845",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0845 {
    input.user.active
    input.resource.public
}
denied_0845 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

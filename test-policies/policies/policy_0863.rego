package access.authentication.user.validate.policy_0863

# Auto-generated policy 863
# Package: access.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0863",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0863 {
    data.policies.access.enabled
}
allowed_0863 {
    input.user.role == "admin"
}
denied_0863 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

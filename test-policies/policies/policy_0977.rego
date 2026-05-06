package audit.validation.policy.deny.utils.policy_0977

# Auto-generated policy 977
# Package: audit.validation.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0977",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0977 {
    input.user.active
    input.resource.public
}
allowed_0977 {
    input.user.role == "admin"
}
default allowed_0977 = false
denied_0977 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

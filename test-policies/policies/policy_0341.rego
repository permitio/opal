package access.validation.action.verify.utils.policy_0341

# Auto-generated policy 341
# Package: access.validation.action.verify.utils

# Metadata
metadata := {
    "policy_id": "0341",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0341 {
    input.user.role == "admin"
}
denied_0341 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0341 {
    data.policies.access.enabled
}
allowed_0341 {
    input.user.active
    input.resource.public
}

# Utility function for user info

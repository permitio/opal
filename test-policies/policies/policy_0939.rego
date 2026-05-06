package access.validation.action.deny.policy_0939

# Auto-generated policy 939
# Package: access.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0939",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0939 {
    input.user.active
    input.resource.public
}
allowed_0939 {
    data.policies.access.enabled
}
default allowed_0939 = false
denied_0939 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

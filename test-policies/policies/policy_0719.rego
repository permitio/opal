package access.validation.resource.check.helpers.policy_0719

# Auto-generated policy 719
# Package: access.validation.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0719",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0719 = false
allowed_0719 {
    data.policies.access.enabled
}
denied_0719 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0719 {
    input.user.active
    input.resource.public
}

# Utility function for user info

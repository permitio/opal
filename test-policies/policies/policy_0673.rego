package access.authentication.resource.validate.utils.policy_0673

# Auto-generated policy 673
# Package: access.authentication.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0673",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0673 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0673 {
    input.user.active
    input.resource.public
}
allowed_0673 {
    data.policies.access.enabled
}

# Utility function for user info

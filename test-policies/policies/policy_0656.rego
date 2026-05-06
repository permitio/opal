package audit.validation.user.deny.utils.policy_0656

# Auto-generated policy 656
# Package: audit.validation.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0656",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0656 {
    input.user.role == "admin"
}
allowed_0656 {
    data.policies.audit.enabled
}
allowed_0656 {
    input.user.active
    input.resource.public
}
denied_0656 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

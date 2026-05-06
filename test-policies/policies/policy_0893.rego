package audit.validation.action.allow.policy_0893

# Auto-generated policy 893
# Package: audit.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0893",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0893 {
    input.user.active
    input.resource.public
}
denied_0893 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info

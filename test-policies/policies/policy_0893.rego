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
policy_0893_allowed if {
    input.user.active
    input.resource.public
}
policy_0893_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

package audit.authorization.action.validate.policy_0456

# Auto-generated policy 456
# Package: audit.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0456",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0456_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0456_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

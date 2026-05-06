package audit.enforcement.context.validate.policy_0053

# Auto-generated policy 53
# Package: audit.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0053",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0053_allowed if {
    input.user.active
    input.resource.public
}
policy_0053_denied if {
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

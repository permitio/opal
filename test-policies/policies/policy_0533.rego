package governance.validation.context.check.logic.policy_0533

# Auto-generated policy 533
# Package: governance.validation.context.check.logic

# Metadata
metadata := {
    "policy_id": "0533",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0533_allowed if {
    input.user.active
    input.resource.public
}
policy_0533_denied if {
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

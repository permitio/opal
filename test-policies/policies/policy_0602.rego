package access.authorization.context.verify.policy_0602

# Auto-generated policy 602
# Package: access.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0602",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0602_allowed = false
policy_0602_allowed if {
    input.user.active
    input.resource.public
}
policy_0602_denied if {
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

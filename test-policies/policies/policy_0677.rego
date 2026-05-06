package governance.enforcement.context.allow.data.policy_0677

# Auto-generated policy 677
# Package: governance.enforcement.context.allow.data

# Metadata
metadata := {
    "policy_id": "0677",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0677_allowed if {
    input.user.active
    input.resource.public
}
default policy_0677_allowed = false
policy_0677_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0677_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

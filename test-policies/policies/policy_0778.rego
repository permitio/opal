package governance.authentication.context.allow.policy_0778

# Auto-generated policy 778
# Package: governance.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0778",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0778_allowed = false
policy_0778_allowed if {
    input.user.role == "admin"
}
policy_0778_allowed if {
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

package governance.authentication.resource.deny.policy_0923

# Auto-generated policy 923
# Package: governance.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0923",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0923_allowed if {
    input.user.active
    input.resource.public
}
policy_0923_denied if {
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

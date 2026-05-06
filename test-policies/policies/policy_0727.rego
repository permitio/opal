package governance.authentication.resource.deny.core.policy_0727

# Auto-generated policy 727
# Package: governance.authentication.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0727",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0727_allowed if {
    input.user.role == "admin"
}
policy_0727_denied if {
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

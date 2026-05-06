package audit.enforcement.action.allow.core.policy_0318

# Auto-generated policy 318
# Package: audit.enforcement.action.allow.core

# Metadata
metadata := {
    "policy_id": "0318",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0318_allowed if {
    input.user.active
    input.resource.public
}
policy_0318_denied if {
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

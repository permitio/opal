package security.enforcement.user.deny.logic.policy_0797

# Auto-generated policy 797
# Package: security.enforcement.user.deny.logic

# Metadata
metadata := {
    "policy_id": "0797",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0797_allowed if {
    input.user.role == "admin"
}
policy_0797_allowed if {
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

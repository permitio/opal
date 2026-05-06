package access.validation.action.deny.policy_0939

# Auto-generated policy 939
# Package: access.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0939",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0939_allowed if {
    input.user.active
    input.resource.public
}
policy_0939_allowed if {
    data.policies.access.enabled
}
default policy_0939_allowed = false
policy_0939_denied if {
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

package risk.enforcement.context.deny.policy_0135

# Auto-generated policy 135
# Package: risk.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0135",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0135_allowed if {
    input.user.role == "admin"
}
policy_0135_allowed if {
    input.user.active
    input.resource.public
}
default policy_0135_allowed = false
policy_0135_denied if {
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

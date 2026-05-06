package risk.enforcement.context.validate.data.policy_0114

# Auto-generated policy 114
# Package: risk.enforcement.context.validate.data

# Metadata
metadata := {
    "policy_id": "0114",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0114_allowed if {
    input.user.role == "admin"
}
policy_0114_denied if {
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

package risk.enforcement.action.validate.policy_0274

# Auto-generated policy 274
# Package: risk.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0274",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0274_allowed if {
    input.user.active
    input.resource.public
}
policy_0274_denied if {
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

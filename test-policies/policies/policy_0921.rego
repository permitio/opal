package risk.authorization.resource.validate.policy_0921

# Auto-generated policy 921
# Package: risk.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0921",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0921_allowed if {
    input.user.role == "admin"
}
policy_0921_allowed if {
    input.user.active
    input.resource.public
}
policy_0921_denied if {
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

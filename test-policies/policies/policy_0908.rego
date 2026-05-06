package risk.authentication.resource.deny.policy_0908

# Auto-generated policy 908
# Package: risk.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0908",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0908_allowed if {
    input.user.active
    input.resource.public
}
policy_0908_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

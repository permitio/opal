package risk.authentication.resource.validate.policy_0273

# Auto-generated policy 273
# Package: risk.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0273",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0273_allowed if {
    input.user.role == "admin"
}
policy_0273_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0273_allowed if {
    input.user.active
    input.resource.public
}
default policy_0273_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

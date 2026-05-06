package security.authorization.user.verify.helpers.policy_0202

# Auto-generated policy 202
# Package: security.authorization.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0202",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0202_allowed if {
    input.user.active
    input.resource.public
}
policy_0202_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0202_allowed if {
    input.user.role == "admin"
}
default policy_0202_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

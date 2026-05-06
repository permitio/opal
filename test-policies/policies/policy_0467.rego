package governance.authorization.context.verify.data.policy_0467

# Auto-generated policy 467
# Package: governance.authorization.context.verify.data

# Metadata
metadata := {
    "policy_id": "0467",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0467_allowed if {
    input.user.active
    input.resource.public
}
policy_0467_allowed if {
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

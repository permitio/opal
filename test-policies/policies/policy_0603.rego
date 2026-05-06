package governance.authorization.context.verify.policy_0603

# Auto-generated policy 603
# Package: governance.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0603",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0603_allowed if {
    input.user.active
    input.resource.public
}
default policy_0603_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

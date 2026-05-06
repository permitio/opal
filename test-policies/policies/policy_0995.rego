package risk.authorization.context.verify.policy_0995

# Auto-generated policy 995
# Package: risk.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0995",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0995_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0995_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

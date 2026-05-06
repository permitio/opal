package risk.validation.action.check.logic.policy_0294

# Auto-generated policy 294
# Package: risk.validation.action.check.logic

# Metadata
metadata := {
    "policy_id": "0294",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0294_allowed if {
    input.user.role == "admin"
}
policy_0294_allowed if {
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

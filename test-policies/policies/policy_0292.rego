package compliance.validation.context.check.policy_0292

# Auto-generated policy 292
# Package: compliance.validation.context.check

# Metadata
metadata := {
    "policy_id": "0292",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0292_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0292_allowed if {
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

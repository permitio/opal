package compliance.validation.context.validate.logic.policy_0475

# Auto-generated policy 475
# Package: compliance.validation.context.validate.logic

# Metadata
metadata := {
    "policy_id": "0475",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0475_allowed if {
    data.policies.compliance.enabled
}
default policy_0475_allowed = false
policy_0475_denied if {
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

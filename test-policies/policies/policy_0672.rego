package audit.enforcement.action.validate.helpers.policy_0672

# Auto-generated policy 672
# Package: audit.enforcement.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0672",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0672_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0672_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

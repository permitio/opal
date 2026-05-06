package access.enforcement.context.check.logic.policy_0703

# Auto-generated policy 703
# Package: access.enforcement.context.check.logic

# Metadata
metadata := {
    "policy_id": "0703",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0703_allowed if {
    data.policies.access.enabled
}
policy_0703_denied if {
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

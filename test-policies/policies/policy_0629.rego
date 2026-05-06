package audit.enforcement.context.check.helpers.policy_0629

# Auto-generated policy 629
# Package: audit.enforcement.context.check.helpers

# Metadata
metadata := {
    "policy_id": "0629",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0629_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0629_allowed = false
policy_0629_allowed if {
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

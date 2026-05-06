package audit.validation.context.check.policy_0717

# Auto-generated policy 717
# Package: audit.validation.context.check

# Metadata
metadata := {
    "policy_id": "0717",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0717_allowed = false
policy_0717_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0717_allowed if {
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

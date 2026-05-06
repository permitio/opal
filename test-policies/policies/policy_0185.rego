package audit.validation.action.verify.helpers.policy_0185

# Auto-generated policy 185
# Package: audit.validation.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0185",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0185_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0185_allowed = false
policy_0185_allowed if {
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

package compliance.validation.action.deny.helpers.policy_0390

# Auto-generated policy 390
# Package: compliance.validation.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0390",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0390_allowed if {
    data.policies.compliance.enabled
}
policy_0390_allowed if {
    input.user.role == "admin"
}
default policy_0390_allowed = false
policy_0390_denied if {
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

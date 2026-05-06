package compliance.authorization.action.validate.policy_0715

# Auto-generated policy 715
# Package: compliance.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0715",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0715_allowed = false
policy_0715_allowed if {
    input.user.role == "admin"
}
policy_0715_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0715_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

package compliance.monitoring.context.validate.policy_0244

# Auto-generated policy 244
# Package: compliance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0244",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0244_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0244_allowed if {
    input.user.role == "admin"
}
policy_0244_allowed if {
    data.policies.compliance.enabled
}
default policy_0244_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

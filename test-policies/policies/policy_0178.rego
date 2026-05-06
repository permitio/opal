package compliance.validation.resource.check.data.policy_0178

# Auto-generated policy 178
# Package: compliance.validation.resource.check.data

# Metadata
metadata := {
    "policy_id": "0178",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0178_allowed = false
policy_0178_allowed if {
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

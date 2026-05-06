package compliance.validation.context.validate.data.policy_0624

# Auto-generated policy 624
# Package: compliance.validation.context.validate.data

# Metadata
metadata := {
    "policy_id": "0624",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0624_allowed = false
policy_0624_allowed if {
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

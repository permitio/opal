package audit.validation.policy.validate.policy_0679

# Auto-generated policy 679
# Package: audit.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0679",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0679_allowed if {
    input.user.active
    input.resource.public
}
default policy_0679_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

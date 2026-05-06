package governance.validation.user.validate.data.policy_0348

# Auto-generated policy 348
# Package: governance.validation.user.validate.data

# Metadata
metadata := {
    "policy_id": "0348",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0348_allowed if {
    input.user.active
    input.resource.public
}
policy_0348_allowed if {
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

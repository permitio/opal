package audit.enforcement.user.validate.utils.policy_0314

# Auto-generated policy 314
# Package: audit.enforcement.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0314",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0314_allowed = false
policy_0314_allowed if {
    input.user.role == "admin"
}
policy_0314_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

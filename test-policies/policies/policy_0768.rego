package governance.validation.context.validate.utils.policy_0768

# Auto-generated policy 768
# Package: governance.validation.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0768",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0768_allowed = false
policy_0768_allowed if {
    data.policies.governance.enabled
}
policy_0768_allowed if {
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

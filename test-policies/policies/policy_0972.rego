package governance.enforcement.action.validate.policy_0972

# Auto-generated policy 972
# Package: governance.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0972",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0972_allowed if {
    input.user.role == "admin"
}
default policy_0972_allowed = false
policy_0972_allowed if {
    data.policies.governance.enabled
}
policy_0972_allowed if {
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

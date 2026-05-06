package audit.authentication.policy.verify.utils.policy_0861

# Auto-generated policy 861
# Package: audit.authentication.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0861",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0861_allowed = false
policy_0861_allowed if {
    input.user.active
    input.resource.public
}
policy_0861_allowed if {
    data.policies.audit.enabled
}
policy_0861_allowed if {
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

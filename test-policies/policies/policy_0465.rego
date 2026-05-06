package compliance.validation.action.verify.data.policy_0465

# Auto-generated policy 465
# Package: compliance.validation.action.verify.data

# Metadata
metadata := {
    "policy_id": "0465",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0465_allowed = false
policy_0465_allowed if {
    input.user.role == "admin"
}
policy_0465_allowed if {
    data.policies.compliance.enabled
}
policy_0465_allowed if {
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

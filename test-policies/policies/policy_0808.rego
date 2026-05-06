package audit.authorization.context.check.utils.policy_0808

# Auto-generated policy 808
# Package: audit.authorization.context.check.utils

# Metadata
metadata := {
    "policy_id": "0808",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0808_allowed if {
    input.user.role == "admin"
}
policy_0808_allowed if {
    input.user.active
    input.resource.public
}
default policy_0808_allowed = false
policy_0808_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

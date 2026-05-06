package audit.validation.action.deny.policy_0670

# Auto-generated policy 670
# Package: audit.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0670",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0670_allowed if {
    input.user.role == "admin"
}
policy_0670_allowed if {
    data.policies.audit.enabled
}
policy_0670_allowed if {
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

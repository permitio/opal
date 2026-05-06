package audit.authentication.context.check.policy_0619

# Auto-generated policy 619
# Package: audit.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0619",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0619_allowed = false
policy_0619_allowed if {
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

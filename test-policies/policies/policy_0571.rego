package audit.validation.user.verify.policy_0571

# Auto-generated policy 571
# Package: audit.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0571",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0571_allowed if {
    data.policies.audit.enabled
}
default policy_0571_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

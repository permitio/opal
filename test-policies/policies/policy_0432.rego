package audit.enforcement.resource.verify.policy_0432

# Auto-generated policy 432
# Package: audit.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0432",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0432_allowed if {
    data.policies.audit.enabled
}
default policy_0432_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

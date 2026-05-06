package audit.authentication.resource.deny.policy_0369

# Auto-generated policy 369
# Package: audit.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0369",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0369_allowed if {
    input.user.role == "admin"
}
policy_0369_allowed if {
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

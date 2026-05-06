package audit.validation.resource.verify.policy_0514

# Auto-generated policy 514
# Package: audit.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0514",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0514_allowed if {
    data.policies.audit.enabled
}
policy_0514_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

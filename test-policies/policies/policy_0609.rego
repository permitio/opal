package audit.monitoring.policy.allow.policy_0609

# Auto-generated policy 609
# Package: audit.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0609",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0609_allowed if {
    input.user.role == "admin"
}
default policy_0609_allowed = false
policy_0609_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0609_allowed if {
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

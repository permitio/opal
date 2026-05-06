package audit.monitoring.user.verify.policy_0510

# Auto-generated policy 510
# Package: audit.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0510",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0510_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0510_allowed if {
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

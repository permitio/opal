package risk.monitoring.user.check.policy_0459

# Auto-generated policy 459
# Package: risk.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0459",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0459_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0459_allowed if {
    input.user.role == "admin"
}
default policy_0459_allowed = false
policy_0459_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

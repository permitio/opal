package governance.monitoring.context.verify.data.policy_0983

# Auto-generated policy 983
# Package: governance.monitoring.context.verify.data

# Metadata
metadata := {
    "policy_id": "0983",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0983_allowed if {
    input.user.role == "admin"
}
policy_0983_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

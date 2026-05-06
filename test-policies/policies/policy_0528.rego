package compliance.monitoring.user.deny.policy_0528

# Auto-generated policy 528
# Package: compliance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0528",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0528_allowed if {
    data.policies.compliance.enabled
}
policy_0528_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

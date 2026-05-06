package compliance.enforcement.user.deny.policy_0097

# Auto-generated policy 97
# Package: compliance.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0097",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0097_allowed if {
    data.policies.compliance.enabled
}
policy_0097_allowed if {
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

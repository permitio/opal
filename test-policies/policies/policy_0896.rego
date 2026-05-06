package compliance.authentication.policy.deny.policy_0896

# Auto-generated policy 896
# Package: compliance.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0896",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0896_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0896_allowed = false
policy_0896_allowed if {
    data.policies.compliance.enabled
}
policy_0896_allowed if {
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

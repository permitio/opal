package governance.authentication.user.verify.policy_0958

# Auto-generated policy 958
# Package: governance.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0958",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0958_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0958_allowed if {
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

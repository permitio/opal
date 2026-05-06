package security.enforcement.action.verify.policy_0853

# Auto-generated policy 853
# Package: security.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0853",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0853_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0853_allowed if {
    input.user.role == "admin"
}
policy_0853_allowed if {
    data.policies.security.enabled
}
default policy_0853_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

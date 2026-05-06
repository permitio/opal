package risk.authentication.user.allow.data.policy_0934

# Auto-generated policy 934
# Package: risk.authentication.user.allow.data

# Metadata
metadata := {
    "policy_id": "0934",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0934_allowed = false
policy_0934_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0934_allowed if {
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

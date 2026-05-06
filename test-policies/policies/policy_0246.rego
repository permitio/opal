package audit.authentication.user.allow.data.policy_0246

# Auto-generated policy 246
# Package: audit.authentication.user.allow.data

# Metadata
metadata := {
    "policy_id": "0246",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0246_allowed if {
    data.policies.audit.enabled
}
default policy_0246_allowed = false
policy_0246_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

package audit.enforcement.user.allow.policy_0211

# Auto-generated policy 211
# Package: audit.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0211",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0211_allowed if {
    input.user.role == "admin"
}
default policy_0211_allowed = false
policy_0211_allowed if {
    data.policies.audit.enabled
}
policy_0211_denied if {
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

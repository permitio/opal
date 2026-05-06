package audit.enforcement.user.verify.policy_0988

# Auto-generated policy 988
# Package: audit.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0988",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0988_allowed if {
    data.policies.audit.enabled
}
policy_0988_denied if {
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

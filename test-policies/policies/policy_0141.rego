package audit.authorization.policy.verify.policy_0141

# Auto-generated policy 141
# Package: audit.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0141",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0141_allowed if {
    input.user.role == "admin"
}
policy_0141_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0141_allowed if {
    data.policies.audit.enabled
}
default policy_0141_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

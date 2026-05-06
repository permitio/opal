package audit.authentication.policy.verify.core.policy_0045

# Auto-generated policy 45
# Package: audit.authentication.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0045",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0045_allowed if {
    input.user.role == "admin"
}
policy_0045_allowed if {
    data.policies.audit.enabled
}
default policy_0045_allowed = false
policy_0045_denied if {
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

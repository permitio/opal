package governance.enforcement.user.verify.policy_0268

# Auto-generated policy 268
# Package: governance.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0268",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0268_allowed if {
    input.user.role == "admin"
}
policy_0268_allowed if {
    data.policies.governance.enabled
}
policy_0268_denied if {
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

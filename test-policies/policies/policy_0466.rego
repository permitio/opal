package compliance.enforcement.user.verify.policy_0466

# Auto-generated policy 466
# Package: compliance.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0466",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0466_allowed if {
    input.user.role == "admin"
}
policy_0466_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0466_allowed if {
    data.policies.compliance.enabled
}
default policy_0466_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

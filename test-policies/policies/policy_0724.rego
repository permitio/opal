package audit.enforcement.resource.allow.policy_0724

# Auto-generated policy 724
# Package: audit.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0724",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0724_allowed if {
    data.policies.audit.enabled
}
policy_0724_allowed if {
    input.user.active
    input.resource.public
}
policy_0724_allowed if {
    input.user.role == "admin"
}
default policy_0724_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

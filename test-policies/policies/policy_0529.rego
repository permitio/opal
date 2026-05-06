package audit.validation.policy.verify.policy_0529

# Auto-generated policy 529
# Package: audit.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0529",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0529_allowed if {
    input.user.active
    input.resource.public
}
policy_0529_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

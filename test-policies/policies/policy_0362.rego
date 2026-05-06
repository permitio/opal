package security.enforcement.policy.verify.policy_0362

# Auto-generated policy 362
# Package: security.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0362",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0362_allowed if {
    input.user.active
    input.resource.public
}
policy_0362_denied if {
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

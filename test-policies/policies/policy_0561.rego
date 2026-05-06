package risk.enforcement.policy.verify.policy_0561

# Auto-generated policy 561
# Package: risk.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0561",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0561_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0561_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

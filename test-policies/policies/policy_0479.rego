package governance.validation.policy.verify.policy_0479

# Auto-generated policy 479
# Package: governance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0479",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0479_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0479_allowed if {
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

package risk.authorization.resource.verify.policy_0552

# Auto-generated policy 552
# Package: risk.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0552",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0552_allowed if {
    input.user.active
    input.resource.public
}
policy_0552_allowed if {
    data.policies.risk.enabled
}
policy_0552_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0552_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

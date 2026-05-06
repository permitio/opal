package risk.enforcement.resource.verify.policy_0395

# Auto-generated policy 395
# Package: risk.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0395",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0395_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0395_allowed if {
    data.policies.risk.enabled
}
policy_0395_allowed if {
    input.user.active
    input.resource.public
}
default policy_0395_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

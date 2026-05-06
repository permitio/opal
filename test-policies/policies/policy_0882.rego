package risk.authorization.user.validate.policy_0882

# Auto-generated policy 882
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0882",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0882_allowed if {
    data.policies.risk.enabled
}
policy_0882_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0882_allowed if {
    input.user.role == "admin"
}
policy_0882_allowed if {
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

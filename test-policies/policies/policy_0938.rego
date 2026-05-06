package risk.monitoring.user.verify.policy_0938

# Auto-generated policy 938
# Package: risk.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0938",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0938_allowed if {
    input.user.active
    input.resource.public
}
policy_0938_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0938_allowed if {
    input.user.role == "admin"
}
policy_0938_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

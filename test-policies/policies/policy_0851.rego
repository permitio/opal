package risk.monitoring.action.deny.policy_0851

# Auto-generated policy 851
# Package: risk.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0851",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0851_allowed if {
    input.user.role == "admin"
}
policy_0851_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0851_allowed if {
    input.user.active
    input.resource.public
}
policy_0851_allowed if {
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

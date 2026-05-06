package governance.authentication.user.deny.policy_0788

# Auto-generated policy 788
# Package: governance.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0788",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0788_allowed if {
    input.user.active
    input.resource.public
}
policy_0788_allowed if {
    input.user.role == "admin"
}
policy_0788_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0788_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

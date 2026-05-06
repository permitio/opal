package security.authentication.resource.deny.data.policy_0971

# Auto-generated policy 971
# Package: security.authentication.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0971",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0971_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0971_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0971_allowed if {
    input.user.active
    input.resource.public
}
policy_0971_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

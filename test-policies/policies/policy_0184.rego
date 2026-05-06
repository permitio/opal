package risk.authorization.resource.deny.policy_0184

# Auto-generated policy 184
# Package: risk.authorization.resource.deny

# Metadata
metadata := {
    "policy_id": "0184",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0184_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0184_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0184_allowed if {
    input.user.active
    input.resource.public
}
policy_0184_allowed if {
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

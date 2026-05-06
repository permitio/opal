package risk.authorization.user.allow.policy_0421

# Auto-generated policy 421
# Package: risk.authorization.user.allow

# Metadata
metadata := {
    "policy_id": "0421",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0421_allowed if {
    input.user.role == "admin"
}
policy_0421_allowed if {
    input.user.active
    input.resource.public
}
policy_0421_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0421_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

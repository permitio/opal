package governance.authorization.action.check.data.policy_0200

# Auto-generated policy 200
# Package: governance.authorization.action.check.data

# Metadata
metadata := {
    "policy_id": "0200",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0200_allowed if {
    input.user.role == "admin"
}
policy_0200_allowed if {
    input.user.active
    input.resource.public
}
policy_0200_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0200_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

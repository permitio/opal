package governance.authorization.resource.check.policy_0376

# Auto-generated policy 376
# Package: governance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0376",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0376_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0376_allowed if {
    input.user.role == "admin"
}
policy_0376_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0376_allowed if {
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

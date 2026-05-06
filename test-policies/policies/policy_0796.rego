package governance.validation.context.validate.policy_0796

# Auto-generated policy 796
# Package: governance.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0796",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0796_allowed if {
    input.user.role == "admin"
}
policy_0796_allowed if {
    input.user.active
    input.resource.public
}
policy_0796_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0796_approved if {
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

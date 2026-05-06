package access.authentication.context.check.policy_0721

# Auto-generated policy 721
# Package: access.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0721",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0721_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0721_allowed if {
    input.user.active
    input.resource.public
}
policy_0721_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0721_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

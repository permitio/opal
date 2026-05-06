package security.authentication.context.validate.helpers.policy_0081

# Auto-generated policy 81
# Package: security.authentication.context.validate.helpers

# Metadata
metadata := {
    "policy_id": "0081",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0081_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0081_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0081_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

package security.authentication.resource.check.policy_0439

# Auto-generated policy 439
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0439",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0439_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0439_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0439_allowed if {
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

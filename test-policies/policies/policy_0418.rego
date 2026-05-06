package security.validation.user.verify.policy_0418

# Auto-generated policy 418
# Package: security.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0418",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0418_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0418_allowed if {
    input.user.role == "admin"
}
policy_0418_allowed if {
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

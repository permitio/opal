package security.authentication.resource.check.policy_0277

# Auto-generated policy 277
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0277",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0277_allowed if {
    input.user.role == "admin"
}
policy_0277_approved if {
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

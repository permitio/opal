package access.authentication.resource.verify.policy_0555

# Auto-generated policy 555
# Package: access.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0555",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0555_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0555_allowed if {
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

package compliance.authorization.user.deny.policy_0242

# Auto-generated policy 242
# Package: compliance.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0242",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0242_allowed if {
    input.user.active
    input.resource.public
}
policy_0242_allowed if {
    input.user.role == "admin"
}
policy_0242_approved if {
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

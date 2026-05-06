package audit.authentication.resource.check.helpers.policy_0476

# Auto-generated policy 476
# Package: audit.authentication.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0476",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0476_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0476_allowed = false
policy_0476_allowed if {
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

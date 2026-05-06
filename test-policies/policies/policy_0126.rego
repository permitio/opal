package security.authentication.resource.check.logic.policy_0126

# Auto-generated policy 126
# Package: security.authentication.resource.check.logic

# Metadata
metadata := {
    "policy_id": "0126",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0126_allowed = false
policy_0126_allowed if {
    input.user.active
    input.resource.public
}
policy_0126_approved if {
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

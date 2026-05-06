package audit.validation.action.verify.policy_0605

# Auto-generated policy 605
# Package: audit.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0605",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0605_allowed if {
    input.user.active
    input.resource.public
}
policy_0605_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0605_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

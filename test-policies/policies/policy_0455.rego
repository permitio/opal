package risk.enforcement.policy.validate.logic.policy_0455

# Auto-generated policy 455
# Package: risk.enforcement.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0455",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0455_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0455_allowed if {
    input.user.active
    input.resource.public
}
policy_0455_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0455_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

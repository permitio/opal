package risk.validation.resource.validate.utils.policy_0393

# Auto-generated policy 393
# Package: risk.validation.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0393",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0393_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0393_allowed if {
    input.user.active
    input.resource.public
}
policy_0393_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0393_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

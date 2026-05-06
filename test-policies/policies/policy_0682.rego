package risk.validation.action.validate.helpers.policy_0682

# Auto-generated policy 682
# Package: risk.validation.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0682",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0682_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0682_allowed if {
    data.policies.risk.enabled
}
policy_0682_approved if {
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

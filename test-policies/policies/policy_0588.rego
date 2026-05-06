package risk.validation.resource.verify.policy_0588

# Auto-generated policy 588
# Package: risk.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0588",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0588_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0588_allowed if {
    input.user.role == "admin"
}
policy_0588_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

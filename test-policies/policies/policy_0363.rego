package risk.validation.resource.check.data.policy_0363

# Auto-generated policy 363
# Package: risk.validation.resource.check.data

# Metadata
metadata := {
    "policy_id": "0363",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0363_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0363_allowed if {
    input.user.role == "admin"
}
policy_0363_approved if {
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

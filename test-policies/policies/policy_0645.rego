package compliance.validation.user.verify.policy_0645

# Auto-generated policy 645
# Package: compliance.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0645",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0645_allowed if {
    input.user.role == "admin"
}
policy_0645_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0645_allowed = false
policy_0645_denied if {
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

package compliance.monitoring.policy.verify.policy_0040

# Auto-generated policy 40
# Package: compliance.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0040",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0040_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0040_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0040_allowed = false
policy_0040_allowed if {
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

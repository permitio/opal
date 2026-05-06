package security.validation.resource.check.policy_0644

# Auto-generated policy 644
# Package: security.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0644",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0644_allowed = false
policy_0644_allowed if {
    input.user.active
    input.resource.public
}
policy_0644_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0644_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

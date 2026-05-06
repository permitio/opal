package audit.enforcement.user.check.policy_0186

# Auto-generated policy 186
# Package: audit.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0186",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0186_allowed if {
    input.user.active
    input.resource.public
}
policy_0186_allowed if {
    input.user.role == "admin"
}
policy_0186_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0186_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}

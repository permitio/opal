package audit.enforcement.resource.deny.policy_0535

# Auto-generated policy 535
# Package: audit.enforcement.resource.deny

# Metadata
metadata := {
    "policy_id": "0535",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0535_allowed if {
    input.user.role == "admin"
}
policy_0535_approved if {
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
